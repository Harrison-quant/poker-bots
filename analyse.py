"""Turn tournament results into tables.

python analyse.py results/dev_roundrobin.json
python analyse.py results/holdout_<hero>.json --holdout
"""
import json
import sys
from collections import defaultdict

from tournament import summarise


def load(path):
    with open(path) as f:
        return json.load(f)


def pair_table(res):
    """Return {a: {b: (bb100, ci)}} from a's point of view for every match."""
    t = defaultdict(dict)
    for key, per_deck in res["results"].items():
        a, b = key.split("|")
        m, ci = summarise(per_deck)
        t[a][b] = (m, ci)
        t[b][a] = (-m, ci)
    return t


def dev_report(res):
    t = pair_table(res)
    names = list(t)
    rows = []
    for a in names:
        vals = [t[a][b][0] for b in names if b != a]
        wins = sum(v > 0 for v in vals)
        sig_wins = sum(t[a][b][0] - t[a][b][1] > 0 for b in names if b != a)
        sig_loss = sum(t[a][b][0] + t[a][b][1] < 0 for b in names if b != a)
        rows.append((sum(vals) / len(vals), a, wins, sig_wins, sig_loss, min(vals)))
    rows.sort(reverse=True)
    hands = res["decks"] * 2
    print(f"Round-robin: {len(names)} bots, {hands} hands per match (duplicate)\n")
    print(f"{'Rank':<5}{'Bot':<16}{'Avg bb/100':>11}{'Beats':>7}{'Sig W':>7}{'Sig L':>7}{'Worst':>9}")
    for i, (avg, a, w, sw, sl, worst) in enumerate(rows, 1):
        print(f"{i:<5}{a:<16}{avg:>11.0f}{w:>5}/{len(names)-1}{sw:>7}{sl:>7}{worst:>9.0f}")
    return rows, t


def holdout_report(res):
    t = pair_table(res)
    holdout = sorted({k.split("|")[1] for k in res["results"]})
    heroes = [k.split("|")[0] for k in res["results"]]
    heroes = list(dict.fromkeys(heroes))
    rows = []
    for h in heroes:
        vals = [t[h][o][0] for o in holdout]
        rows.append((sum(vals) / len(vals), h, sum(v > 0 for v in vals)))
    rows.sort(reverse=True)
    print(f"Holdout: vs {len(holdout)} frozen bots, {res['decks']*2} hands per match\n")
    print(f"{'Rank':<5}{'Bot':<16}{'Avg bb/100':>11}{'Beats':>7}")
    for i, (avg, h, w) in enumerate(rows, 1):
        print(f"{i:<5}{h:<16}{avg:>11.0f}{w:>5}/{len(holdout)}")
    return rows, t


if __name__ == "__main__":
    res = load(sys.argv[1])
    if "--holdout" in sys.argv:
        holdout_report(res)
    else:
        dev_report(res)
