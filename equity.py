"""Hand equity: the chance a hand wins at showdown.

Equity = P(win) + 0.5 * P(tie). Everything here is counting/simulation over
the cards we can't see, i.e. the Year 11 combinatorics assignment, automated.

- Preflop: a lookup table for all 169 starting-hand types vs a random hand,
  built once by simulation and cached to disk.
- Postflop: Monte Carlo. Deal the opponent random cards and the rest of the
  board many times and count how often we win. Results are cached, because
  every bot sees the same decks, so each (hand, board) is only simulated once.
- Range equity: same, but the opponent's cards are drawn only from the top X%
  of starting hands (used by bots that assume a bettor has a strong hand).
"""
import json
import os
import random
import zlib
from functools import lru_cache
from itertools import combinations

from phevaluator import evaluate_cards  # fast C hand evaluator; lower rank = stronger

RANKS = "23456789TJQKA"
SUITS = "cdhs"
DECK = [r + s for r in RANKS for s in SUITS]
CARD_ID = {c: i for i, c in enumerate(DECK)}  # rank*4 + suit, matches phevaluator
ALL_COMBOS = list(combinations(range(52), 2))  # 1326 two-card hands

_TABLE_PATH = os.path.join(os.path.dirname(__file__), "data", "preflop_equity.json")


def hand_class(c1, c2):
    """'AKs', 'AKo' or 'AA' for two cards (strings)."""
    r1, r2 = RANKS.index(c1[0]), RANKS.index(c2[0])
    if r1 < r2:
        c1, c2, r1, r2 = c2, c1, r2, r1
    if r1 == r2:
        return c1[0] + c2[0]
    return c1[0] + c2[0] + ("s" if c1[1] == c2[1] else "o")


def _class_of_ids(a, b):
    return hand_class(DECK[a], DECK[b])


def _mc_equity_ids(hole, board, n, rng, opp_pool=None):
    """Monte Carlo equity for card ids. opp_pool: list of allowed opponent combos."""
    dead = set(hole) | set(board)
    rest = [c for c in range(52) if c not in dead]
    need = 5 - len(board)
    wins = 0.0
    if opp_pool is not None:
        pool = [p for p in opp_pool if p[0] not in dead and p[1] not in dead]
    for _ in range(n):
        if opp_pool is None:
            draw = rng.sample(rest, 2 + need)
            opp = draw[:2]
            runout = draw[2:]
        else:
            opp = rng.choice(pool)
            rest2 = [c for c in rest if c != opp[0] and c != opp[1]]
            runout = rng.sample(rest2, need)
        full = list(board) + runout
        me = evaluate_cards(*hole, *full)
        op = evaluate_cards(*opp, *full)
        if me < op:
            wins += 1
        elif me == op:
            wins += 0.5
    return wins / n


def _river_exact_ids(hole, board, opp_pool=None):
    """On the river there is nothing left to deal: enumerate every opponent hand exactly."""
    dead = set(hole) | set(board)
    me = evaluate_cards(*hole, *board)
    wins = 0.0
    total = 0
    pool = opp_pool if opp_pool is not None else ALL_COMBOS
    for a, b in pool:
        if a in dead or b in dead:
            continue
        op = evaluate_cards(a, b, *board)
        total += 1
        if me < op:
            wins += 1
        elif me == op:
            wins += 0.5
    return wins / total if total else 0.5


# ---------- preflop table ----------

def build_preflop_table(samples=40000, seed=1):
    rng = random.Random(seed)
    table = {}
    done = set()
    for a, b in ALL_COMBOS:
        cls = _class_of_ids(a, b)
        if cls in done:
            continue
        done.add(cls)
        table[cls] = _mc_equity_ids([a, b], [], samples, rng)
    os.makedirs(os.path.dirname(_TABLE_PATH), exist_ok=True)
    with open(_TABLE_PATH, "w") as f:
        json.dump(table, f, indent=0, sort_keys=True)
    return table


def _load_table():
    if not os.path.exists(_TABLE_PATH):
        return build_preflop_table()
    with open(_TABLE_PATH) as f:
        return json.load(f)


PREFLOP = _load_table()
# Classes sorted strongest first, and each class's percentile (0 = best hand).
_ORDER = sorted(PREFLOP, key=lambda c: -PREFLOP[c])
_COMBOS_PER_CLASS = {c: (6 if len(c) == 2 else 4 if c[2] == "s" else 12) for c in PREFLOP}
PERCENTILE = {}
_cum = 0
for c in _ORDER:
    PERCENTILE[c] = (_cum + _COMBOS_PER_CLASS[c] / 2) / 1326
    _cum += _COMBOS_PER_CLASS[c]


def preflop_percentile(hole):
    """0.0 = best starting hand (AA), 1.0 = worst (72o)."""
    return PERCENTILE[hand_class(*hole)]


@lru_cache(maxsize=None)
def _top_range(frac):
    """All 1326 combos whose class is in the top `frac` of starting hands."""
    frac = max(frac, 0.03)
    keep = {c for c in PREFLOP if PERCENTILE[c] <= frac}
    return [p for p in ALL_COMBOS if _class_of_ids(*p) in keep]


# ---------- public API (cards are strings like 'As') ----------

@lru_cache(maxsize=500000)
def _equity_cached(hole, board, frac, n):
    h = [CARD_ID[c] for c in hole]
    b = [CARD_ID[c] for c in board]
    pool = None if frac >= 1.0 else _top_range(round(frac, 2))
    if len(b) == 0 and pool is None:
        return PREFLOP[hand_class(*hole)]
    if len(b) == 5:
        return _river_exact_ids(h, b, pool)
    # deterministic seed per situation so results don't depend on call order
    rng = random.Random(zlib.crc32(f"{hole}{board}{frac}".encode()))
    return _mc_equity_ids(h, b, n, rng, pool)


def equity(hole, board, vs_top=1.0, n=400):
    """Equity of `hole` given `board` against a random hand (vs_top=1.0)
    or against a hand from the top `vs_top` fraction of starting hands."""
    return _equity_cached(tuple(sorted(hole)), tuple(sorted(board)), round(vs_top, 2), n)


# ---------- multiway (3+ players) ----------
# With k opponents the raw chance of winning is much lower (AA wins ~49% vs 5 random
# hands). Raw equity is the right number for pot-odds calls. For "how strong is my hand"
# thresholds, we convert k-way equity to the heads-up scale by percentile: a hand that
# ranks in the top 10% six-handed gets the same strength as a top-10% hand heads-up.

def _mc_multi_ids(hole, board, n_opp, n, rng, first_pool=None):
    """Equity vs n_opp opponents. If first_pool is given, opponent 1 comes from that range
    (the player who bet) and the rest are random. Ties split the pot."""
    dead = set(hole) | set(board)
    rest = [c for c in range(52) if c not in dead]
    need = 5 - len(board)
    if first_pool is not None:
        pool = [p for p in first_pool if p[0] not in dead and p[1] not in dead]
    share = 0.0
    for _ in range(n):
        if first_pool is None:
            draw = rng.sample(rest, 2 * n_opp + need)
            opps = [draw[2 * i:2 * i + 2] for i in range(n_opp)]
            runout = draw[2 * n_opp:]
        else:
            o1 = rng.choice(pool)
            rest2 = [c for c in rest if c != o1[0] and c != o1[1]]
            draw = rng.sample(rest2, 2 * (n_opp - 1) + need)
            opps = [list(o1)] + [draw[2 * i:2 * i + 2] for i in range(n_opp - 1)]
            runout = draw[2 * (n_opp - 1):]
        full = list(board) + runout
        me = evaluate_cards(*hole, *full)
        best = min(evaluate_cards(*o, *full) for o in opps)
        if me < best:
            share += 1
        elif me == best:
            ties = 1 + sum(evaluate_cards(*o, *full) == me for o in opps)
            share += 1 / ties
    return share / n


_MULTI_PATH = os.path.join(os.path.dirname(__file__), "data", "preflop_equity_multi.json")


def _build_multi_tables(samples=6000, seed=3):
    """Preflop equity for every starting hand vs 2..5 random opponents."""
    rng = random.Random(seed)
    reps = {}
    for a, b in ALL_COMBOS:
        reps.setdefault(_class_of_ids(a, b), [a, b])
    out = {}
    for k in range(2, 6):
        out[str(k)] = {cls: _mc_multi_ids(h, [], k, samples, rng) for cls, h in reps.items()}
    with open(_MULTI_PATH, "w") as f:
        json.dump(out, f, indent=0, sort_keys=True)
    return out


def _load_multi():
    if not os.path.exists(_MULTI_PATH):
        return _build_multi_tables()
    with open(_MULTI_PATH) as f:
        return json.load(f)


PREFLOP_MULTI = None
_CURVES = {}


def _curve(k):
    """Monotone map from k-way equity to heads-up equity, matched by combo-weighted percentile."""
    global PREFLOP_MULTI
    if k in _CURVES:
        return _CURVES[k]
    if PREFLOP_MULTI is None:
        PREFLOP_MULTI = _load_multi()
    tab = PREFLOP_MULTI[str(k)]
    # walk both orderings from weakest to strongest, matching cumulative combo counts
    hu_sorted = sorted(PREFLOP, key=lambda c: PREFLOP[c])
    k_sorted = sorted(tab, key=lambda c: tab[c])
    hu_pts, cum = [], 0
    for c in hu_sorted:
        cum += _COMBOS_PER_CLASS[c]
        hu_pts.append((cum / 1326, PREFLOP[c]))
    xs, ys, cum = [0.0], [0.0], 0
    j = 0
    for c in k_sorted:
        cum += _COMBOS_PER_CLASS[c]
        p = cum / 1326
        while hu_pts[j][0] < p - 1e-9:
            j += 1
        xs.append(tab[c])
        ys.append(hu_pts[j][1])
    xs.append(1.0)
    ys.append(1.0)
    _CURVES[k] = (xs, ys)
    return xs, ys


def to_hu_scale(e, n_opp):
    """Convert equity vs n_opp opponents to the equivalent heads-up strength."""
    if n_opp <= 1:
        return e
    xs, ys = _curve(min(n_opp, 5))
    for i in range(1, len(xs)):
        if e <= xs[i]:
            x0, x1, y0, y1 = xs[i - 1], xs[i], ys[i - 1], ys[i]
            return y0 if x1 == x0 else y0 + (y1 - y0) * (e - x0) / (x1 - x0)
    return 1.0


@lru_cache(maxsize=500000)
def _multi_cached(hole, board, n_opp, frac, n):
    h = [CARD_ID[c] for c in hole]
    b = [CARD_ID[c] for c in board]
    if len(b) == 0 and frac >= 1.0:
        global PREFLOP_MULTI
        if PREFLOP_MULTI is None:
            PREFLOP_MULTI = _load_multi()
        return PREFLOP_MULTI[str(min(n_opp, 5))][hand_class(*hole)]
    pool = None if frac >= 1.0 else _top_range(round(frac, 2))
    rng = random.Random(zlib.crc32(f"{hole}{board}{frac}{n_opp}".encode()))
    return _mc_multi_ids(h, b, n_opp, n, rng, pool)


def equity_multi(hole, board, n_opp, vs_top=1.0, n=300):
    """Raw equity vs n_opp opponents (heads-up path unchanged when n_opp == 1)."""
    if n_opp <= 1:
        return equity(hole, board, vs_top=vs_top)
    return _multi_cached(tuple(sorted(hole)), tuple(sorted(board)), n_opp, round(vs_top, 2), n)


if __name__ == "__main__":
    # Sanity checks against well-known heads-up numbers
    for h in ["AA", "KK", "AKs", "AKo", "TT", "72o", "32o"]:
        print(f"{h:4s} vs random: {PREFLOP[h]*100:5.1f}%   percentile {PERCENTILE[h]*100:5.1f}%")
