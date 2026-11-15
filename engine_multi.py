"""Multi-player (e.g. 6-max) No-Limit Hold'em engine.

Same idea as engine.py, but for N players. Defaults match a normal online 6-max
cash game: blinds 50/100, 100 big blinds deep, stacks reset every hand.

Seat rotation (the multiway version of duplicate): each deck is played N times,
rotating the bots one seat each time, so every bot gets every seat's cards and
position once. Luck from the cards largely cancels across the rotation.
"""
import warnings

from pokerkit import NoLimitTexasHoldem

from engine import _AUTO, BB, SB

warnings.filterwarnings("ignore", module="pokerkit")

STACK_MULTI = 10000  # 100 big blinds


def play_hand_multi(bots, deck, stack=STACK_MULTI):
    """bots[s] sits in PokerKit seat s (0 = small blind, 1 = big blind, last = button).
    deck: 2*N hole cards (seat order) then 5 board cards. Returns chips won per seat."""
    n = len(bots)
    st = NoLimitTexasHoldem.create_state(_AUTO, True, 0, (SB, BB), BB, (stack,) * n, n)
    holes = [tuple(deck[2 * s:2 * s + 2]) for s in range(n)]
    for h in holes:
        st.deal_hole(h[0] + h[1])
    board_cards = deck[2 * n:2 * n + 5]
    for s, b in enumerate(bots):
        b.new_hand(is_button=(s == n - 1))
    history = []

    while st.status:
        if st.can_deal_board():
            k = sum(len(r) for r in st.board_cards)
            m = 3 if k == 0 else 1
            st.deal_board("".join(board_cards[k:k + m]))
            continue
        i = st.actor_index
        if i is None:
            break
        k = sum(len(r) for r in st.board_cards)
        board = tuple(board_cards[:k])
        street = {0: 0, 3: 1, 4: 2, 5: 3}[k]
        others = [j for j in range(n) if j != i and st.statuses[j]]
        to_call = st.checking_or_calling_amount or 0
        can_raise = st.can_complete_bet_or_raise_to()
        obs = {
            "hole": holes[i],
            "board": board,
            "street": street,
            "pot": sum(st.pot_amounts) + sum(st.bets),
            "to_call": to_call,
            "my_bet": st.bets[i],
            "opp_bet": max(st.bets[j] for j in others),   # the bet to match
            "my_stack": st.stacks[i],
            "opp_stack": max(st.stacks[j] for j in others),
            "n_opp": len(others),                          # opponents still in the hand
            "can_raise": can_raise,
            "min_raise_to": st.min_completion_betting_or_raising_to_amount if can_raise else None,
            "max_raise_to": st.max_completion_betting_or_raising_to_amount if can_raise else None,
            "is_button": i == n - 1,
            "history": list(history),
            "bb": BB,
        }
        act = bots[i].act(obs)
        if act[0] == "f" and to_call > 0:
            st.fold()
            history.append((i, street, "f", 0))
        elif act[0] == "r" and can_raise:
            amt = max(obs["min_raise_to"], min(obs["max_raise_to"], int(round(act[1]))))
            st.complete_bet_or_raise_to(amt)
            history.append((i, street, "r", amt))
        else:
            st.check_or_call()
            history.append((i, street, "c", to_call))
        for j in range(n):
            if j != i:
                bots[j].see_opponent(history[-1], obs)

    pay = list(st.payoffs)
    for s, b in enumerate(bots):
        b.end_hand(pay[s], None)
    return pay


def play_rotation(bots, deck):
    """Play one deck N times, rotating seats. Returns total chips won by each bot (in input order)."""
    n = len(bots)
    totals = [0] * n
    for r in range(n):
        seating = [bots[(s + r) % n] for s in range(n)]   # bot in each seat this time
        pay = play_hand_multi(seating, deck)
        for s in range(n):
            totals[(s + r) % n] += pay[s]
    return totals
