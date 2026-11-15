"""Offline test of the Slumbot client.

A mock server speaks Slumbot's API format (action strings, client_pos, winnings),
with one of our own bots playing the Slumbot seat. Every hand played through the
client must give exactly the same chips as the same hand in the tournament engine.
If the replay, the observation or the action conversion were wrong anywhere, results
would differ.

    python test_slumbot_client.py
"""
import os
import tempfile
import warnings

from pokerkit import NoLimitTexasHoldem

from bots import AllIn, CallingStation, LAG, Maniac, PotOddsRange, Rock, TAG, Trapper
from engine import _AUTO, BB, SB, STACK, play_hand
from slumbot_client import STREET_OF, _dealt, make_obs, run, to_incr
from tournament import make_decks

warnings.filterwarnings("ignore")


class MockSlumbot:
    """Plays `opp` in Slumbot's seat and answers in Slumbot's JSON format."""

    def __init__(self, opp, deals):
        self.opp, self.deals = opp, list(deals)

    def new_hand(self, token):
        self.deck, self.cpos = self.deals.pop(0)
        self.st = NoLimitTexasHoldem.create_state(_AUTO, True, 0, (SB, BB), BB, (STACK, STACK), 2)
        self.holes = [tuple(self.deck[0:2]), tuple(self.deck[2:4])]  # seat 0 = BB, seat 1 = button
        self.st.deal_hole("".join(self.holes[0]))
        self.st.deal_hole("".join(self.holes[1]))
        self.board_cards = self.deck[4:9]
        self.action, self.street_in_str, self.history = "", 0, []
        self.opp.new_hand(is_button=(1 - self.cpos == 1))
        return self._advance()

    def _apply(self, incr):
        st = self.st
        street = STREET_OF[_dealt(st)]
        if street > self.street_in_str:
            self.action += "/" * (street - self.street_in_str)
            self.street_in_str = street
        seat = st.actor_index
        if incr in ("k", "c"):
            if incr == "k" and (st.checking_or_calling_amount or 0) > 0:
                return {"error_msg": "Illegal check"}
            amt = st.checking_or_calling_amount or 0
            st.check_or_call()
            self.history.append((seat, street, "c", amt))
        elif incr == "f":
            st.fold()
            self.history.append((seat, street, "f", 0))
        elif incr.startswith("b"):
            amt = int(incr[1:])
            try:
                st.complete_bet_or_raise_to(amt)
            except ValueError as e:
                return {"error_msg": f"Illegal bet: {e}"}
            self.history.append((seat, street, "r", amt))
        else:
            return {"error_msg": "Bad incr"}
        self.action += incr
        return None

    def _advance(self):
        st = self.st
        while st.status:
            if st.can_deal_board():
                k = _dealt(st)
                st.deal_board("".join(self.board_cards[k:k + (3 if k == 0 else 1)]))
                continue
            i = st.actor_index
            if i is None or i == self.cpos:
                break
            obs = make_obs(st, i, self.holes, self.board_cards, self.history)
            self._apply(to_incr(self.opp.act(obs), obs))
        k = _dealt(st)
        if st.status and STREET_OF[k] > self.street_in_str:  # Slumbot puts the slash in before our turn
            self.action += "/" * (STREET_OF[k] - self.street_in_str)
            self.street_in_str = STREET_OF[k]
        r = {"action": self.action, "client_pos": self.cpos, "hole_cards": list(self.holes[self.cpos]),
             "board": list(self.board_cards[:k]), "token": "mock-token"}
        if not st.status:
            r["winnings"] = st.payoffs[self.cpos]
            r["baseline_winnings"] = 0
            showdown = not self.history or self.history[-1][2] != "f"
            if showdown:
                r["bot_hole_cards"] = list(self.holes[1 - self.cpos])
        return r

    def act(self, token, incr):
        err = self._apply(incr)
        return err or self._advance()


def check(hero_cls, opp_cls, n=300, seed=3):
    decks = make_decks(n, seed)
    deals = [(d, h % 2) for h, d in enumerate(decks)]  # alternate positions like Slumbot
    expected = []
    hero, opp = hero_cls(), opp_cls()  # one instance each, as in the client run (keeps random draws in step)
    for d, cpos in deals:
        bb_bot, btn_bot = (hero, opp) if cpos == 0 else (opp, hero)
        x, y = play_hand(bb_bot, btn_bot, d)
        expected.append(x if cpos == 0 else y)
    path = os.path.join(tempfile.mkdtemp(), "t.jsonl")
    got = run(hero_cls(), n, path, api=MockSlumbot(opp_cls(), deals), quiet=True)
    assert got == expected, (hero_cls.__name__, opp_cls.__name__,
                             next(i for i, (a, b) in enumerate(zip(got, expected)) if a != b))
    return n


if __name__ == "__main__":
    total = 0
    for hero in (Trapper, PotOddsRange):
        for opp in (AllIn, Maniac, CallingStation, Rock, TAG, LAG, Trapper, PotOddsRange):
            total += check(hero, opp)
    print(f"client matches engine on all {total} hands")

    # resume: stop part way, rerun, same final log
    decks = make_decks(50, 9)
    deals = [(d, h % 2) for h, d in enumerate(decks)]
    path = os.path.join(tempfile.mkdtemp(), "r.jsonl")
    run(Trapper(), 20, path, api=MockSlumbot(Rock(), deals), quiet=True)
    wins = run(Trapper(), 50, path, api=MockSlumbot(Rock(), deals[20:]), quiet=True)
    assert len(wins) == 50 and len(open(path).read().splitlines()) == 50
    print("resume ok")
