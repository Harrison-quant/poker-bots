"""Equity calculator: your chance of winning from any point in a hand.

    python equity_calc.py AsKs                 # preflop vs a random hand
    python equity_calc.py AsKs QsJh2d          # on the flop
    python equity_calc.py AsKs QsJh2d --vs 0.2 # vs a hand from the top 20% of starting hands
"""
import argparse

from equity import equity, hand_class, preflop_percentile


def split(s):
    return tuple(s[i:i + 2] for i in range(0, len(s), 2))


ap = argparse.ArgumentParser()
ap.add_argument("hole")
ap.add_argument("board", nargs="?", default="")
ap.add_argument("--vs", type=float, default=1.0, help="opponent range: top fraction of hands")
ap.add_argument("-n", type=int, default=20000, help="simulations")
a = ap.parse_args()
hole, board = split(a.hole), split(a.board)
e = equity(hole, board, vs_top=a.vs, n=a.n)
print(f"{hand_class(*hole)} (top {preflop_percentile(hole)*100:.0f}% of starting hands)")
print(f"Equity vs {'random hand' if a.vs >= 1 else f'top {a.vs*100:.0f}%'}: {e*100:.1f}%")
