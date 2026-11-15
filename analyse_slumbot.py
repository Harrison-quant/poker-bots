"""Summarise Slumbot results.  python analyse_slumbot.py results/slumbot_*.jsonl

Main result: raw bb/100 (what the bot actually won).

All-in EV (secondary, unbiased): when both players are all-in before the river, the cards
still to come are pure luck. We replace the actual result of those hands with the
average result over every possible run-out (the hand's equity x the pot). This removes
some of the luck without biasing the answer.

Slumbot's baseline_winnings is shown for reference only. It is NOT used: its average
is clearly not zero here or in other people's Slumbot benchmarks, so subtracting it
biases the result upward.
"""
import json
import math
import random
import sys
from itertools import combinations

from phevaluator import evaluate_cards

from equity import DECK
from slumbot_client import _dealt, replay

BB = 100


def ci(x):
    n = len(x)
    m = sum(x) / n
    sd = math.sqrt(sum((v - m) ** 2 for v in x) / (n - 1)) if n > 1 else 0.0
    return m / BB * 100, 1.96 * sd / math.sqrt(n) / BB * 100


def line(label, x):
    if len(x) < 2:
        return f"  {label:<34}{len(x):>6} hands"
    m, c = ci(x)
    return f"  {label:<34}{len(x):>6} hands {m:>+7.0f} bb/100  (+/- {c:.0f})"


def _showdown_share(me, opp, board, rng, samples=20000):
    """Our expected share of the pot (win = 1, tie = 0.5) over all run-outs."""
    dead = set(me) | set(opp) | set(board)
    rest = [c for c in DECK if c not in dead]
    need = 5 - len(board)
    if need <= 2:
        runouts = combinations(rest, need)
    else:  # preflop all-in: too many run-outs to list, so sample them
        runouts = (rng.sample(rest, need) for _ in range(samples))
    tot = n = 0
    for ro in runouts:
        full = list(board) + list(ro)
        a, b = evaluate_cards(*me, *full), evaluate_cards(*opp, *full)
        tot += 1.0 if a < b else 0.5 if a == b else 0.0
        n += 1
    return tot / n


def allin_ev(r, rng):
    """Expected winnings for a hand that went all-in before the river, else actual winnings."""
    a = r["action"]
    if a.endswith("f") or not r.get("slumbot_hole") or len(r.get("board") or []) < 5:
        return r["winnings"]
    # Find the call that put both players all-in. Replay the action up to each call, giving
    # the replay only the board cards that were out on that street, and check the stacks.
    for cut in range(len(a)):
        if a[cut] != "c":
            continue
        prefix = a[:cut + 1]
        k = [0, 3, 4, 5][min(prefix.count("/"), 3)]  # board cards out on this street
        if k >= 5:
            return r["winnings"]  # all-in on the river: no cards left to come, nothing to adjust
        st, _, _ = replay(prefix, r["client_pos"], r["hole"], r["board"][:k])
        if st.stacks[0] == 0 and st.stacks[1] == 0:
            put_in = 20000  # equal 200bb stacks, so both full stacks are in
            share = _showdown_share(r["hole"], r["slumbot_hole"], r["board"][:k], rng)
            return share * 2 * put_in - put_in
    return r["winnings"]


def report(path):
    recs = [json.loads(l) for l in open(path) if l.strip()]
    rng = random.Random(1)
    raw = [r["winnings"] for r in recs]
    ev = [allin_ev(r, rng) for r in recs]
    base = [r["baseline_winnings"] for r in recs if r.get("baseline_winnings") is not None]
    out = [path]
    out.append(line("Raw (main result)", raw))
    out.append(line("All-in EV adjusted", ev))
    out.append(f"  {'All-in before river':<34}{sum(e != w for e, w in zip(ev, raw)):>6} hands adjusted")
    if base:
        out.append(line("Slumbot baseline (should be ~0)", base))
    for pos, lab in [(1, "As button (small blind)"), (0, "As big blind")]:
        out.append(line(lab + ", all-in EV", [e for e, r in zip(ev, recs) if r["client_pos"] == pos]))
    folded = [r for r in recs if r["action"].endswith("f")]
    sd = [e for e, r in zip(ev, recs) if not r["action"].endswith("f")]
    out.append(line("Went to showdown, all-in EV", sd))
    out.append(line("We folded", [r["winnings"] for r in folded if r["winnings"] < 0]))
    out.append(line("Slumbot folded", [r["winnings"] for r in folded if r["winnings"] > 0]))
    big = [r for r in recs if abs(r["winnings"]) >= 10000]
    out.append(f"  Pots of 100bb+ won/lost: {sum(r['winnings'] > 0 for r in big)}/{sum(r['winnings'] < 0 for r in big)}")
    return "\n".join(out)


if __name__ == "__main__":
    for p in sys.argv[1:]:
        print(report(p))
        print()
