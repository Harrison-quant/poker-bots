"""FROZEN holdout opponents. Written 2026-10-31 before any tournament result was seen.

These are only used once, to test the bot that wins the development round-robin.
They are deliberately built differently from the development roster (chart-based
preflop, check-raising, polarised overbets, probe bets, random thresholds), so a
bot that merely learned to beat the dev field won't automatically beat them.

Do not edit after the first holdout run.
"""
from bots import Bot, all_in, check_fold, eq, eq_raw, pot_odds, raise_pot
from equity import preflop_percentile


class NitShover(Bot):
    """Folds everything except the top 5%, then shoves."""
    name = "H_NitShover"

    def act(self, obs):
        if preflop_percentile(obs["hole"]) < 0.05:
            return all_in(obs)
        return check_fold(obs)


class ProbeBettor(Bot):
    """Bets 1/3 pot whenever checked to; folds to aggression unless equity > 65%."""
    name = "H_ProbeBettor"

    def act(self, obs):
        if obs["to_call"] == 0:
            return raise_pot(obs, 0.33)
        if obs["street"] == 0 and obs["to_call"] <= obs["bb"]:
            return ("c",)
        return ("c",) if eq(obs) > 0.65 else check_fold(obs)


class CheckRaiser(Bot):
    """Checks first, then check-raises strong hands (eq > 70%) and 20% of weak ones as bluffs."""
    name = "H_CheckRaiser"

    def act(self, obs):
        e = eq(obs)
        if obs["street"] == 0:
            return ("c",) if preflop_percentile(obs["hole"]) < 0.6 or obs["to_call"] == 0 else check_fold(obs)
        if obs["to_call"] == 0:
            return ("c",)
        if e > 0.70 or (e < 0.30 and self.rng.random() < 0.20):
            return raise_pot(obs, 1.0)
        return ("c",) if eq_raw(obs) > pot_odds(obs) else check_fold(obs)


class RangeReg(Bot):
    """Chart-style regular: button opens top 45% to 2.5bb, BB defends top 60% vs opens,
    3-bets top 8%; postflop c-bets half pot 60% of the time, continues on pot odds."""
    name = "H_RangeReg"

    def __init__(self, seed=0):
        super().__init__(seed)
        self.aggressor = False

    def new_hand(self, is_button):
        self.aggressor = False

    def act(self, obs):
        if obs["street"] == 0:
            p = preflop_percentile(obs["hole"])
            if p < 0.08:
                self.aggressor = True
                return raise_pot(obs, 1.0)
            unopened = obs["opp_bet"] <= obs["bb"]
            if obs["is_button"] and unopened:
                if p < 0.45:
                    self.aggressor = True
                    return ("r", 2.5 * obs["bb"])
                return check_fold(obs)
            if obs["to_call"] == 0:
                return ("c",)
            limit = 0.60 if obs["to_call"] <= 3 * obs["bb"] else 0.25
            return ("c",) if p < limit else check_fold(obs)
        e = eq(obs)
        if obs["to_call"] == 0:
            if e > 0.70 or (self.aggressor and self.rng.random() < 0.60):
                self.aggressor = False
                return raise_pot(obs, 0.5)
            return ("c",)
        if e > 0.80:
            return raise_pot(obs, 0.9)
        return ("c",) if eq_raw(obs) > pot_odds(obs) + 0.05 else check_fold(obs)


class Overbettor(Bot):
    """Polarised: bets 2x pot with very strong (eq > 75%) or very weak (eq < 20%) hands,
    checks the middle, calls on pot odds."""
    name = "H_Overbettor"

    def act(self, obs):
        e = eq(obs)
        if obs["to_call"] == 0 and (e > 0.75 or e < 0.20):
            return raise_pot(obs, 2.0)
        if obs["to_call"] > 0 and e > 0.85:
            return all_in(obs)
        return ("c",) if obs["to_call"] == 0 or eq_raw(obs) > pot_odds(obs) else check_fold(obs)


class StickyCaller(Bot):
    """Calls down unless equity < 25%; raises only on the river with equity > 85%."""
    name = "H_StickyCaller"

    def act(self, obs):
        e = eq(obs)
        if obs["street"] == 3 and e > 0.85:
            return raise_pot(obs, 1.0)
        return ("c",) if e > 0.25 or obs["to_call"] == 0 else check_fold(obs)


class JitterLadder(Bot):
    """Equity ladder whose thresholds are redrawn at random every hand."""
    name = "H_JitterLadder"

    def new_hand(self, is_button):
        a = self.rng.uniform(0.30, 0.50)
        self.t = (a, a + self.rng.uniform(0.08, 0.2), 0, 0)
        self.t = (self.t[0], self.t[1], self.t[1] + self.rng.uniform(0.05, 0.15), 0)
        self.t = (*self.t[:3], self.t[2] + self.rng.uniform(0.05, 0.15))

    def act(self, obs):
        a, b, c, d = self.t
        e = eq(obs)
        if e >= d:
            return all_in(obs)
        if e >= c:
            return raise_pot(obs, 1.0)
        if e >= b:
            return raise_pot(obs, 0.5)
        return ("c",) if e >= a else check_fold(obs)


class Limper(Bot):
    """Always calls preflop; postflop plays strict pot odds with a 2/3-pot value bet."""
    name = "H_Limper"

    def act(self, obs):
        if obs["street"] == 0:
            return ("c",)
        e = eq(obs)
        if obs["to_call"] == 0:
            return raise_pot(obs, 0.66) if e > 0.65 else ("c",)
        return ("c",) if eq_raw(obs) > pot_odds(obs) else check_fold(obs)


def holdout_roster(seed=0):
    return [NitShover(seed), ProbeBettor(seed), CheckRaiser(seed), RangeReg(seed),
            Overbettor(seed), StickyCaller(seed), JitterLadder(seed), Limper(seed)]
