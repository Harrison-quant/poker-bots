"""Rank bots from 6-max results. python analyse_multi.py results/multi6_A.json [results/multi6_B.json]"""
import json
import math
import sys
from collections import defaultdict


def scores(path):
    d = json.load(open(path))
    per = defaultdict(list)
    for t in d["tables"]:
        for nm, v in zip(t["lineup"], t["bb100"]):
            per[nm].append(v)
    out = {}
    for nm, v in per.items():
        m = sum(v) / len(v)
        sd = math.sqrt(sum((x - m) ** 2 for x in v) / (len(v) - 1))
        out[nm] = (m, 1.96 * sd / math.sqrt(len(v)), len(v))
    return out


def ranks(s):
    order = sorted(s, key=lambda n: -s[n][0])
    return {n: i + 1 for i, n in enumerate(order)}, order


if __name__ == "__main__":
    a = scores(sys.argv[1])
    ra, order = ranks(a)
    b = scores(sys.argv[2]) if len(sys.argv) > 2 else None
    rb = ranks(b)[0] if b else None
    hdr = f"{'Rank':<5}{'Bot':<16}{'A bb/100':>10}{'+/-':>6}{'Tables':>8}"
    if b:
        hdr += f"{'B bb/100':>10}{'+/-':>6}{'B rank':>8}"
    print(hdr)
    for n in order:
        m, ci, k = a[n]
        line = f"{ra[n]:<5}{n:<16}{m:>10.0f}{ci:>6.0f}{k:>8}"
        if b:
            line += f"{b[n][0]:>10.0f}{b[n][1]:>6.0f}{rb[n]:>8}"
        print(line)
    if b:
        # Spearman rank correlation between samples
        n = len(order)
        d2 = sum((ra[x] - rb[x]) ** 2 for x in order)
        print(f"\nRank correlation A vs B (Spearman): {1 - 6 * d2 / (n * (n * n - 1)):.2f}")
