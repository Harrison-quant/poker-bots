"""Play one of our bots against Slumbot through its public API.

Run this on your own PC (it needs internet access to slumbot.com):
    pip install pokerkit phevaluator
    python slumbot_client.py --bot Trapper --hands 5000
    python slumbot_client.py --bot PotOddsRange --hands 5000

Every finished hand is appended to results/slumbot_<bot>.jsonl. You can stop at any
time (Ctrl+C) and rerun the same command later: it carries on where it left off.

How it works, in plain terms:
- Slumbot sends the betting so far as a short string, e.g. "b250c/kb300".
- We replay that string into a PokerKit game, so the pot, the amount to call and the
  legal raise sizes come from the same rules engine used in our tournaments.
- We ask our bot what to do, exactly as in the tournaments, and send the answer back.

Slumbot's format: k = check, c = call, f = fold, bN = bet/raise so the bettor has N in
for this street, / = next street. Blinds 50/100, 200bb stacks, reset every hand.
client_pos 0 = we are the big blind, 1 = we are the small blind (button).
"""
import argparse
import json
import math
import os
import sys
import time
import urllib.error
import urllib.request
import warnings

from pokerkit import NoLimitTexasHoldem

from engine import _AUTO, BB, SB, STACK
from equity import DECK

warnings.filterwarnings("ignore")

HOST = "https://slumbot.com"
STREET_OF = {0: 0, 3: 1, 4: 2, 5: 3}


# ---------------- talking to Slumbot ----------------

def _post(path, data, retries=6):
    body = json.dumps(data).encode()
    err = None
    for k in range(retries):
        try:
            req = urllib.request.Request(
                HOST + path, data=body,
                headers={"Content-Type": "application/json", "User-Agent": "poker-bots-client"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code < 500:  # API errors come back as JSON with an error_msg
                try:
                    return json.loads(e.read().decode())
                except Exception:
                    pass
            err = e
        except Exception as e:  # network blip: wait and retry
            err = e
        time.sleep(min(60, 2 ** k))
    raise RuntimeError(f"request to {path} kept failing: {err}")


class SlumbotAPI:
    def __init__(self, debug=False):
        self.debug = debug

    def _log(self, what, data, r):
        if self.debug:
            print(f"  {what} {json.dumps(data)} -> {json.dumps(r)}")
        return r

    def new_hand(self, token):
        data = {"token": token} if token else {}
        return self._log("new_hand", data, _post("/api/new_hand", data))

    def act(self, token, incr):
        data = {"token": token, "incr": incr}
        return self._log("act", data, _post("/api/act", data))


# ---------------- rebuilding the game from the action string ----------------

def _dealt(st):
    return sum(len(r) for r in st.board_cards)


def make_obs(st, i, holes, board_cards, history):
    """Exactly the observation the tournament engine gives a bot (see engine.py)."""
    k = _dealt(st)
    to_call = st.checking_or_calling_amount or 0
    can_raise = st.can_complete_bet_or_raise_to()
    return {
        "hole": tuple(holes[i]),
        "board": tuple(board_cards[:k]),
        "street": STREET_OF[k],
        "pot": sum(st.pot_amounts) + sum(st.bets),
        "to_call": to_call,
        "my_bet": st.bets[i],
        "opp_bet": st.bets[1 - i],
        "my_stack": st.stacks[i],
        "opp_stack": st.stacks[1 - i],
        "can_raise": can_raise,
        "min_raise_to": st.min_completion_betting_or_raising_to_amount if can_raise else None,
        "max_raise_to": st.max_completion_betting_or_raising_to_amount if can_raise else None,
        "is_button": i == 1,
        "history": list(history),
        "bb": BB,
    }


def replay(action, client_pos, hole, board):
    """Replay Slumbot's action string into a fresh PokerKit game.
    Slumbot's hidden cards are unknown, so placeholder cards stand in for them; our bot
    never sees the opponent's cards, so this has no effect on its decisions."""
    st = NoLimitTexasHoldem.create_state(_AUTO, True, 0, (SB, BB), BB, (STACK, STACK), 2)
    known = set(hole) | set(board)
    holes = [None, None]
    holes[client_pos] = tuple(hole)
    holes[1 - client_pos] = tuple([c for c in DECK if c not in known][:2])
    st.deal_hole("".join(holes[0]))
    st.deal_hole("".join(holes[1]))
    history = []

    def deal_known():
        while st.status and st.can_deal_board():
            k = _dealt(st)
            n = 3 if k == 0 else 1
            if len(board) < k + n:
                return
            st.deal_board("".join(board[k:k + n]))

    i = 0
    while i < len(action):
        ch = action[i]
        if ch == "/":
            i += 1
            continue
        deal_known()
        seat, street = st.actor_index, STREET_OF[_dealt(st)]
        if ch in "kc":
            amt = st.checking_or_calling_amount or 0
            st.check_or_call()
            history.append((seat, street, "c", amt))
            i += 1
        elif ch == "f":
            st.fold()
            history.append((seat, street, "f", 0))
            i += 1
        elif ch == "b":
            j = i + 1
            while j < len(action) and action[j].isdigit():
                j += 1
            amt = int(action[i + 1:j])
            st.complete_bet_or_raise_to(amt)  # raises an error if the bet is illegal
            history.append((seat, street, "r", amt))
            i = j
        else:
            raise ValueError(f"unknown action character {ch!r} in {action!r}")
    deal_known()
    return st, holes, history


def to_incr(act, obs):
    """Turn our bot's decision into Slumbot's format (same clamping as the engine)."""
    kind = act[0]
    if kind == "r" and obs["can_raise"]:
        amt = max(obs["min_raise_to"], min(obs["max_raise_to"], int(round(act[1]))))
        return f"b{amt}"
    if kind == "f" and obs["to_call"] > 0:
        return "f"
    return "c" if obs["to_call"] > 0 else "k"


# ---------------- playing ----------------

class HandError(Exception):
    pass


def _check(r):
    if "error_msg" in r:
        raise HandError(r["error_msg"])
    return r


def play_one(api, bot, token):
    """Play one hand. Returns (token, record)."""
    r = _check(api.new_hand(token))
    token = r.get("token") or token
    pos = r["client_pos"]
    bot.new_hand(is_button=(pos == 1))
    while r.get("winnings") is None:
        board = r.get("board") or []
        st, holes, history = replay(r.get("action", ""), pos, r["hole_cards"], board)
        if st.actor_index != pos:
            raise HandError(f"not our turn after replaying {r.get('action')!r}")
        obs = make_obs(st, pos, holes, board, history)
        incr = to_incr(bot.act(obs), obs)
        r = _check(api.act(token, incr))
        token = r.get("token") or token
    bot.end_hand(r["winnings"], r.get("bot_hole_cards"))
    return token, {
        "client_pos": pos,
        "hole": r.get("hole_cards"),
        "board": r.get("board"),
        "slumbot_hole": r.get("bot_hole_cards"),
        "action": r.get("action"),
        "winnings": r["winnings"],
        # Slumbot's own variance reduction: what Slumbot would have won in our seat with the
        # same cards. winnings - baseline cancels most of the card luck (like duplicate dealing).
        "baseline_winnings": r.get("baseline_winnings"),
    }


def _stat(x):
    n = len(x)
    m = sum(x) / n
    sd = math.sqrt(sum((w - m) ** 2 for w in x) / (n - 1))
    return f"{m / BB * 100:+.0f} bb/100 (+/- {1.96 * sd / math.sqrt(n) / BB * 100:.0f})"


def summary(recs):
    n = len(recs)
    if n < 2:
        return f"{n} hands"
    out = f"{n} hands, raw {_stat([r['winnings'] for r in recs])}"
    adj = [r["winnings"] - r["baseline_winnings"] for r in recs if r.get("baseline_winnings") is not None]
    if len(adj) >= 2:
        out += f", baseline-adjusted {_stat(adj)}"
    return out


def run(bot, hands, out_path, api=None, quiet=False, sleep=0.0):
    api = api or SlumbotAPI()
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    recs = []
    if os.path.exists(out_path):
        with open(out_path) as f:
            recs = [json.loads(line) for line in f if line.strip()]
        if recs and not quiet:
            print(f"Resuming: {summary(recs)} already played")
    token, errors = None, 0
    with open(out_path, "a") as f:
        while len(recs) < hands:
            try:
                token, rec = play_one(api, bot, token)
            except HandError as e:
                errors += 1
                if not quiet:
                    print("Slumbot error:", e)
                token = None  # start fresh on the next hand
                if errors >= 20:
                    print("Too many errors in a row, stopping. Rerun later to continue.")
                    break
                time.sleep(2)
                continue
            errors = 0
            rec["hand"] = len(recs) + 1
            f.write(json.dumps(rec) + "\n")
            f.flush()
            recs.append(rec)
            if not quiet and (len(recs) % 100 == 0 or len(recs) == hands):
                print(summary(recs), flush=True)
            if sleep:
                time.sleep(sleep)
    return [r["winnings"] for r in recs]


def main():
    from bots import dev_roster
    names = [b.name for b in dev_roster()]
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bot", default="Trapper", choices=names)
    ap.add_argument("--hands", type=int, default=5000)
    ap.add_argument("--sleep", type=float, default=0.0, help="pause between hands, seconds")
    ap.add_argument("--debug", action="store_true", help="print every message to and from Slumbot")
    a = ap.parse_args()
    bot = next(b for b in dev_roster() if b.name == a.bot)
    out = os.path.join("results", f"slumbot_{a.bot}.jsonl")
    print(f"{a.bot} vs Slumbot, target {a.hands} hands, logging to {out}")
    try:
        run(bot, a.hands, out, api=SlumbotAPI(debug=a.debug), sleep=a.sleep)
    except KeyboardInterrupt:
        print("\nStopped. Rerun the same command to continue.")
        return
    with open(out) as f:
        print("Done:", summary([json.loads(l) for l in f if l.strip()]))


if __name__ == "__main__":
    sys.exit(main())
