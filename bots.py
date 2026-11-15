"""The development roster: 20 bots.

Each bot gets an `obs` dict from the engine and returns one of:
    ("f",)            fold (turned into a check if there's nothing to call)
    ("c",)            check or call
    ("r", amount)     bet/raise TO this total amount for the street (clamped to legal)

"Equity" below always means the chance of winning at showdown (see equity.py).
"""
import math
import random

from equity import equity_multi, preflop_percentile, to_hu_scale


# ---------------- helpers ----------------

class Bot:
    name = "Bot"

    def __init__(self, seed=0):
        self.rng = random.Random(seed)

    def new_hand(self, is_button):
        pass

    def see_opponent(self, action, obs):
        pass

    def end_hand(self, payoff, opp_cards):
        pass

    def act(self, obs):
        raise NotImplementedError


def eq_raw(obs, vs_top=1.0):
    """True chance of winning vs everyone still in the hand. Use for pot-odds decisions."""
    return equity_multi(obs["hole"], obs["board"], obs.get("n_opp", 1), vs_top=vs_top)


def eq(obs, vs_top=1.0):
    """Hand strength on the heads-up scale (identical to raw equity heads-up).
    Multiway, raw equity is converted by percentile so thresholds keep their meaning."""
    return to_hu_scale(eq_raw(obs, vs_top), obs.get("n_opp", 1))


def raise_pot(obs, frac):
    """Raise to a size that is `frac` of the pot (after calling). frac=1 is a pot-size raise."""
    if not obs["can_raise"]:
        return ("c",)
    pot_after_call = obs["pot"] + obs["to_call"]
    target = obs["opp_bet"] + frac * pot_after_call
    if obs["street"] == 0 and obs["opp_bet"] <= obs["bb"]:
        target = max(target, 2.5 * obs["bb"])  # standard open is 2.5 big blinds
    return ("r", target)


def all_in(obs):
    return ("r", obs["max_raise_to"]) if obs["can_raise"] else ("c",)


def pot_odds(obs):
    """Equity needed to break even on a call: call / (pot after calling)."""
    tc = obs["to_call"]
    return tc / (obs["pot"] + tc) if tc else 0.0


def check_fold(obs):
    return ("f",)  # engine converts to a check when free


# ---------------- 1-7: simple personalities ----------------

class AllIn(Bot):
    """The bot from the competition story: shoves every hand."""
    name = "AllIn"

    def act(self, obs):
        return all_in(obs)


class CallingStation(Bot):
    """Never folds, never raises."""
    name = "CallingStation"

    def act(self, obs):
        return ("c",)


class RandomBot(Bot):
    """Uniformly random between fold, call and a random-sized raise. A floor for 'no skill'."""
    name = "Random"

    def act(self, obs):
        x = self.rng.random()
        if x < 1 / 3:
            return ("f",)
        if x < 2 / 3:
            return ("c",)
        return raise_pot(obs, self.rng.uniform(0.3, 1.5))


class Maniac(Bot):
    """Over-the-top aggressive: pot-size raise every time it can."""
    name = "Maniac"

    def act(self, obs):
        return raise_pot(obs, 1.0)


class Rock(Bot):
    """Very cautious: only plays the top 12% of hands; bets only with very strong equity."""
    name = "Rock"

    def act(self, obs):
        if obs["street"] == 0:
            if preflop_percentile(obs["hole"]) > 0.12:
                return check_fold(obs)
            return raise_pot(obs, 0.75) if preflop_percentile(obs["hole"]) < 0.04 else ("c",)
        e = eq(obs)
        if e > 0.80:
            return raise_pot(obs, 0.75)
        if e > 0.62:
            return ("c",)
        return check_fold(obs)


class TAG(Bot):
    """Tight-aggressive: top 25% preflop, bets good hands, calls with pot odds plus a margin."""
    name = "TAG"

    def act(self, obs):
        if obs["street"] == 0:
            p = preflop_percentile(obs["hole"])
            if p < 0.08:
                return raise_pot(obs, 1.0)
            if p < 0.25:
                return raise_pot(obs, 0.75) if obs["opp_bet"] <= obs["bb"] else (
                    ("c",) if obs["to_call"] <= 4 * obs["bb"] else check_fold(obs))
            if p < 0.40 and obs["to_call"] <= obs["bb"]:
                return ("c",)
            return check_fold(obs)
        e = eq(obs)
        if e > 0.70:
            return raise_pot(obs, 0.66)
        if eq_raw(obs) > pot_odds(obs) + 0.10:
            return ("c",)
        return check_fold(obs)


class LAG(Bot):
    """Loose-aggressive: plays 55% of hands, bets a lot, bluffs 30% when checked to."""
    name = "LAG"

    def act(self, obs):
        if obs["street"] == 0:
            p = preflop_percentile(obs["hole"])
            if p < 0.15:
                return raise_pot(obs, 1.0)
            if p < 0.55:
                return raise_pot(obs, 0.75) if obs["opp_bet"] <= obs["bb"] else (
                    ("c",) if obs["to_call"] <= 6 * obs["bb"] else check_fold(obs))
            return check_fold(obs)
        e = eq(obs)
        if e > 0.60:
            return raise_pot(obs, 0.75)
        if obs["to_call"] == 0 and self.rng.random() < 0.30:
            return raise_pot(obs, 0.6)
        if eq_raw(obs) > pot_odds(obs):
            return ("c",)
        return check_fold(obs)


# ---------------- 8-12: Harrison's equity ladders ----------------

class Ladder(Bot):
    """Threshold ladder on equity vs a random hand:
        below a      -> fold (check if free)
        a  to b      -> check/call
        b  to c      -> raise small_frac x pot
        c  to d      -> raise big_frac x pot
        above d      -> all-in (unless shove=False, then big raise)
    """

    def __init__(self, name, a, b, c, d, small=0.5, big=1.0, shove=True, seed=0):
        super().__init__(seed)
        self.name = name
        self.t = (a, b, c, d)
        self.small, self.big, self.shove = small, big, shove

    def act(self, obs):
        a, b, c, d = self.t
        e = eq(obs)
        if e >= d:
            return all_in(obs) if self.shove else raise_pot(obs, self.big)
        if e >= c:
            return raise_pot(obs, self.big)
        if e >= b:
            return raise_pot(obs, self.small)
        if e >= a:
            return ("c",)
        return check_fold(obs)


# ---------------- 13-20: maths and adaptive bots ----------------

class PotOdds(Bot):
    """The textbook maths bot: call when equity beats the pot odds, value-bet strong hands."""
    name = "PotOdds"

    def act(self, obs):
        e = eq(obs)
        if e > 0.72:
            return raise_pot(obs, 0.8)
        if obs["to_call"] == 0:
            return raise_pot(obs, 0.6) if e > 0.60 else ("c",)
        return ("c",) if eq_raw(obs) > pot_odds(obs) else check_fold(obs)


def _range_after_bet(obs):
    """Rough guess of the opponent's range when they bet: bigger bet relative to pot
    -> stronger range. Returns the top fraction of hands assumed."""
    tc = obs["to_call"]
    if tc == 0:
        return 1.0
    size = tc / max(obs["pot"] - tc, 1)  # their bet as a fraction of the pot before it
    return max(0.10, min(1.0, 0.9 - 0.45 * size))


class PotOddsRange(PotOdds):
    """Same as PotOdds, but when facing a bet it assumes the opponent's hand is from a
    stronger-than-random range, and calls based on equity against that range."""
    name = "PotOddsRange"

    def act(self, obs):
        if obs["to_call"] == 0:
            return super().act(obs)
        e_rand = eq(obs)
        e_rng = eq(obs, vs_top=round(_range_after_bet(obs), 1))
        if e_rng > 0.65 and e_rand > 0.72:
            return raise_pot(obs, 0.8)
        return ("c",) if eq_raw(obs, vs_top=round(_range_after_bet(obs), 1)) > pot_odds(obs) else check_fold(obs)


class Exploiter(Bot):
    """Opponent modelling. Tracks how often the opponent bets/raises and how often they fold
    to our bets, then: trusts aggressive opponents' bets less, passive opponents' bets more,
    value-bets thinner against opponents who never fold, and bluffs more against ones who do."""
    name = "Exploiter"

    def __init__(self, seed=0):
        super().__init__(seed)
        self.opp_actions = 1
        self.opp_raises = 0.5
        self.our_bets = 1
        self.opp_folds = 0.5
        self._bet_pending = False

    def new_hand(self, is_button):
        self._bet_pending = False

    def see_opponent(self, action, obs):
        _, _, kind, _ = action
        self.opp_actions += 1
        if kind == "r":
            self.opp_raises += 1
        if self._bet_pending:
            self.our_bets += 1
            if kind == "f":
                self.opp_folds += 1
            self._bet_pending = False

    def act(self, obs):
        aggr = self.opp_raises / self.opp_actions          # how often they raise
        fold_rate = self.opp_folds / self.our_bets           # how often they fold to our bets
        e = eq(obs)
        if obs["to_call"] > 0:
            # Against maniacs a bet means little (use random-hand equity);
            # against passive players a bet means strength (use range equity).
            trust = max(0.0, min(1.0, (0.45 - aggr) / 0.35))
            e_rng = eq(obs, vs_top=round(_range_after_bet(obs), 1))
            e_used = trust * e_rng + (1 - trust) * e
            if e_used > 0.70:
                return raise_pot(obs, 0.8)
            raw_used = trust * eq_raw(obs, vs_top=round(_range_after_bet(obs), 1)) + (1 - trust) * eq_raw(obs)
            return ("c",) if raw_used > pot_odds(obs) else check_fold(obs)
        value_line = 0.62 - 0.10 * (1 - fold_rate)          # thinner value vs callers
        if e > value_line:
            self._bet_pending = True
            return raise_pot(obs, 0.75)
        if fold_rate > 0.55 and self.rng.random() < 0.5:   # bluff opponents who fold a lot
            self._bet_pending = True
            return raise_pot(obs, 0.6)
        return ("c",)


class Bluffer(PotOdds):
    """PotOdds plus bluffs: when checked to with a weak hand, bets 25% of the time."""
    name = "Bluffer"

    def act(self, obs):
        if obs["to_call"] == 0 and obs["street"] > 0 and eq(obs) < 0.35 and self.rng.random() < 0.25:
            return raise_pot(obs, 0.7)
        return super().act(obs)


class Trapper(PotOdds):
    """Slow-plays monsters: with equity > 80% it just checks/calls until the river, then shoves."""
    name = "Trapper"

    def act(self, obs):
        e = eq(obs)
        if e > 0.80 and obs["street"] < 3:
            return ("c",)
        if e > 0.80:
            return all_in(obs)
        return super().act(obs)


class PushFold(Bot):
    """Preflop only: shove the top 30% of hands, fold the rest."""
    name = "PushFold"

    def act(self, obs):
        if obs["street"] == 0:
            return all_in(obs) if preflop_percentile(obs["hole"]) < 0.30 else check_fold(obs)
        return ("c",)


class MinRaiser(Bot):
    """Min-raises whenever equity > 50%, calls from 40%."""
    name = "MinRaiser"

    def act(self, obs):
        e = eq(obs)
        if e > 0.50 and obs["can_raise"]:
            return ("r", obs["min_raise_to"])
        return ("c",) if e > 0.40 or obs["to_call"] == 0 else check_fold(obs)


class MixedEquity(Bot):
    """Randomised: the stronger the hand, the more likely to raise, with random sizing.
    Harder to read than a fixed ladder."""
    name = "MixedEquity"

    def act(self, obs):
        e = eq(obs)
        p_raise = 1 / (1 + math.exp(-(e - 0.62) * 15))
        if self.rng.random() < p_raise:
            return raise_pot(obs, self.rng.uniform(0.5, 1.2))
        if obs["to_call"] == 0 or eq_raw(obs) > pot_odds(obs) + 0.03:
            return ("c",)
        return check_fold(obs)


def dev_roster(seed=0):
    """Fresh instances of all 20 development bots (fresh = no memory carried over)."""
    return [
        AllIn(seed), CallingStation(seed), RandomBot(seed), Maniac(seed), Rock(seed),
        TAG(seed), LAG(seed),
        Ladder("Ladder_Default", 0.40, 0.55, 0.65, 0.75, seed=seed),
        Ladder("Ladder_Tight", 0.45, 0.60, 0.70, 0.80, seed=seed),
        Ladder("Ladder_Loose", 0.35, 0.50, 0.60, 0.70, seed=seed),
        Ladder("Ladder_NoShove", 0.40, 0.55, 0.65, 0.75, shove=False, seed=seed),
        Ladder("Ladder_BigSizes", 0.40, 0.55, 0.65, 0.75, small=1.0, big=2.0, seed=seed),
        PotOdds(seed), PotOddsRange(seed), Exploiter(seed), Bluffer(seed), Trapper(seed),
        PushFold(seed), MinRaiser(seed), MixedEquity(seed),
    ]
