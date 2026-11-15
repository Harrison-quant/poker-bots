"""Round-robin tournament.

Every pair of bots plays the same set of decks, each deck twice with seats
swapped (duplicate). Every pair uses the SAME decks, so all bots face the same
luck. Results are in big blinds per 100 hands (bb/100), the standard poker
win-rate unit, with a 95% confidence interval.

Usage:
    python tournament.py dev  --decks 2000      # development round-robin
    python tournament.py holdout --hero NAME    # one-off test vs frozen holdout bots
"""
import argparse
import json
import math
import os
import random
import sys
import time
from multiprocessing import Pool

from engine import BB, play_duplicate
from equity import DECK


def make_decks(n, seed):
    rng = random.Random(seed)
    return [rng.sample(DECK, 9) for _ in range(n)]


def _roster(kind):
    if kind == "dev":
        from bots import dev_roster
        return dev_roster
    from holdout_bots import holdout_roster
    return holdout_roster


def _bot(kind_or_dev, name, seed):
    from bots import dev_roster
    from holdout_bots import holdout_roster
    for b in dev_roster(seed) + holdout_roster(seed):
        if b.name == name:
            return b
    raise KeyError(name)


def run_pair(args):
    """Play one match. Fresh bots each match, so no memory leaks between opponents."""
    name_a, name_b, decks, seed = args
    a, b = _bot(None, name_a, seed), _bot(None, name_b, seed + 1)
    per_deck = [play_duplicate(a, b, d) for d in decks]
    return name_a, name_b, per_deck


def summarise(per_deck):
    n = len(per_deck)
    mean = sum(per_deck) / n
    var = sum((x - mean) ** 2 for x in per_deck) / (n - 1)
    hands = 2 * n
    bb100 = sum(per_deck) / BB / hands * 100
    se = math.sqrt(var / n) / BB / 2 * 100  # per-deck = 2 hands
    return bb100, 1.96 * se


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["dev", "holdout", "smoke"])
    ap.add_argument("--decks", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--hero", default=None)
    ap.add_argument("--workers", type=int, default=os.cpu_count())
    args = ap.parse_args()

    decks = make_decks(args.decks, args.seed)
    from bots import dev_roster
    dev_names = [b.name for b in dev_roster()]

    if args.mode in ("dev", "smoke"):
        names = dev_names
        jobs = [(names[i], names[j], decks, args.seed) for i in range(len(names)) for j in range(i + 1, len(names))]
        out_path = "results/dev_roundrobin.json" if args.mode == "dev" else "results/smoke.json"
    else:
        from holdout_bots import holdout_roster
        hold = [b.name for b in holdout_roster()]
        # hero plus the top dev bots as reference points, all vs the frozen holdout bots
        names = [args.hero] + [n for n in dev_names if n != args.hero]
        jobs = [(h, o, decks, args.seed) for h in names for o in hold]
        out_path = f"results/holdout_{args.hero}.json"

    t0 = time.time()
    results = {}
    with Pool(args.workers) as pool:
        for k, (a, b, per_deck) in enumerate(pool.imap_unordered(run_pair, jobs), 1):
            results[f"{a}|{b}"] = per_deck
            if k % 10 == 0 or k == len(jobs):
                print(f"{k}/{len(jobs)} matches, {time.time() - t0:.0f}s", flush=True)

    os.makedirs("results", exist_ok=True)
    with open(out_path, "w") as f:
        json.dump({"decks": args.decks, "seed": args.seed, "results": results}, f)
    print("saved", out_path)


if __name__ == "__main__":
    sys.exit(main())
