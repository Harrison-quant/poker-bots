"""6-max tournament with random line-ups.

Each table is 6 bots drawn at random from the pool of all 28 bots (20 dev + 8 holdout).
Each table plays `decks` decks, each deck rotated through all 6 seats. Every bot's result
at a table is in bb/100; a bot's score is the average over all tables it sat at.
Tables are the independent unit for confidence intervals.

Two independent samples (different line-ups and decks): pick the champion on A,
confirm on B.

    python tournament_multi.py --sample A --tables 300 --decks 40
"""
import argparse
import json
import os
import random
import time
from multiprocessing import Pool

from engine import BB
from engine_multi import play_rotation
from equity import DECK

SEEDS = {"A": 11, "B": 22, "smoke": 99}


def pool_names():
    from bots import dev_roster
    from holdout_bots import holdout_roster
    return [b.name for b in dev_roster() + holdout_roster()]


def _bot(name, seed):
    from bots import dev_roster
    from holdout_bots import holdout_roster
    for b in dev_roster(seed) + holdout_roster(seed):
        if b.name == name:
            return b
    raise KeyError(name)


def run_table(args):
    names, decks, seed = args
    bots = [_bot(nm, seed + i) for i, nm in enumerate(names)]
    totals = [0] * len(bots)
    for d in decks:
        for i, x in enumerate(play_rotation(bots, d)):
            totals[i] += x
    hands = len(decks) * len(bots)
    return names, [t / BB / hands * 100 for t in totals]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", choices=list(SEEDS), default="A")
    ap.add_argument("--tables", type=int, default=300)
    ap.add_argument("--decks", type=int, default=40)
    ap.add_argument("--size", type=int, default=6)
    ap.add_argument("--workers", type=int, default=os.cpu_count())
    a = ap.parse_args()

    rng = random.Random(SEEDS[a.sample])
    names = pool_names()
    jobs = []
    for t in range(a.tables):
        lineup = rng.sample(names, a.size)
        decks = [rng.sample(DECK, 2 * a.size + 5) for _ in range(a.decks)]
        jobs.append((lineup, decks, SEEDS[a.sample] * 1000 + t))

    t0 = time.time()
    tables = []
    with Pool(a.workers) as p:
        for k, (lineup, bb100) in enumerate(p.imap_unordered(run_table, jobs), 1):
            tables.append({"lineup": lineup, "bb100": bb100})
            if k % 25 == 0 or k == len(jobs):
                print(f"{k}/{len(jobs)} tables, {time.time() - t0:.0f}s", flush=True)

    os.makedirs("results", exist_ok=True)
    out = f"results/multi{a.size}_{a.sample}.json"
    with open(out, "w") as f:
        json.dump({"sample": a.sample, "decks": a.decks, "size": a.size, "tables": tables}, f)
    print("saved", out)


if __name__ == "__main__":
    main()
