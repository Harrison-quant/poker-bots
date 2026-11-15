"""Heads-up No-Limit Hold'em engine.

PokerKit enforces the rules (blinds, legal bet sizes, side pots, who wins).
This file just: deals cards from a deck we choose, asks each bot what to do,
and returns how many chips each bot won.

Settings match the Slumbot / ACPC format: blinds 50/100, 200 big blinds deep,
stacks reset every hand.

Duplicate dealing: each deck is played twice with the bots swapping seats, so
both bots get the exact same cards. Luck mostly cancels and the remaining
difference is skill. This cuts the number of hands needed by a lot.
"""
import warnings

from pokerkit import Automation, NoLimitTexasHoldem

warnings.filterwarnings("ignore", module="pokerkit")

SB, BB = 50, 100
STACK = 20000

_AUTO = (
    Automation.ANTE_POSTING,
    Automation.BET_COLLECTION,
    Automation.BLIND_OR_STRADDLE_POSTING,
    Automation.CARD_BURNING,
    Automation.HOLE_CARDS_SHOWING_OR_MUCKING,
    Automation.HAND_KILLING,
    Automation.CHIPS_PUSHING,
    Automation.CHIPS_PULLING,
)


def play_hand(bot_bb, bot_btn, deck):
    """Play one hand. deck = 9 card strings: BB hole (2), button hole (2), board (5).

    In heads-up PokerKit, player 0 is the big blind and player 1 is the
    button/small blind (acts first preflop, last after the flop).
    Returns chips won by (bot_bb, bot_btn).
    """
    st = NoLimitTexasHoldem.create_state(_AUTO, True, 0, (SB, BB), BB, (STACK, STACK), 2)
    st.deal_hole(deck[0] + deck[1])  # big blind's cards
    st.deal_hole(deck[2] + deck[3])  # button's cards
    holes = [tuple(deck[0:2]), tuple(deck[2:4])]
    assert [repr(c) for c in st.hole_cards[0]] == list(holes[0])
    board_cards = deck[4:9]
    bots = [bot_bb, bot_btn]
    history = []  # (seat, street, action, amount_to)
    for i, b in enumerate(bots):
        b.new_hand(is_button=(i == 1))

    while st.status:
        if st.can_deal_board():
            k = len(_board(st))
            n = 3 if k == 0 else 1
            st.deal_board("".join(board_cards[k:k + n]))
            continue
        i = st.actor_index
        if i is None:
            break
        board = tuple(board_cards[: len(_board(st))])
        street = {0: 0, 3: 1, 4: 2, 5: 3}[len(board)]
        pot = sum(st.pot_amounts) + sum(st.bets)
        to_call = st.checking_or_calling_amount or 0
        can_raise = st.can_complete_bet_or_raise_to()
        obs = {
            "hole": holes[i],
            "board": board,
            "street": street,
            "pot": pot,
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
        act = bots[i].act(obs)
        kind = act[0]
        if kind == "f" and to_call > 0:
            st.fold()
            history.append((i, street, "f", 0))
        elif kind == "r" and can_raise:
            amt = int(round(act[1]))
            amt = max(obs["min_raise_to"], min(obs["max_raise_to"], amt))
            st.complete_bet_or_raise_to(amt)
            history.append((i, street, "r", amt))
        else:
            st.check_or_call()
            history.append((i, street, "c", to_call))
        bots[1 - i].see_opponent(history[-1], obs)

    pay = list(st.payoffs)
    showdown = len(history) == 0 or history[-1][2] != "f"
    for i, b in enumerate(bots):
        b.end_hand(pay[i], holes[1 - i] if showdown else None)
    return pay[0], pay[1]


def _board(st):
    return [c for row in st.board_cards for c in row]


def play_duplicate(bot_a, bot_b, deck):
    """Play the deck twice with seats swapped. Returns bot_a's total chips."""
    a1, _ = play_hand(bot_a, bot_b, deck)  # A in the big blind with the BB cards
    _, a2 = play_hand(bot_b, bot_a, deck)  # same cards and board, bots swap seats
    return a1 + a2
