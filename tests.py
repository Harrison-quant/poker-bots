"""Sanity checks for the engine and bots. Run: python tests.py"""
from bots import AllIn, CallingStation, PotOdds, Ladder, dev_roster
from engine import STACK, play_duplicate, play_hand
from holdout_bots import holdout_roster
from tournament import make_decks

decks = make_decks(300, 7)

# 1. Zero-sum: whatever one bot wins, the other loses.
for d in decks[:100]:
    x, y = play_hand(AllIn(), CallingStation(), d)
    assert x + y == 0 and abs(x) <= STACK
print("zero-sum ok")

# 2. Mirror test: a deterministic bot against a copy of itself must net exactly 0
#    under duplicate dealing (same cards, swapped seats). Checks the duplicate setup.
for cls in (PotOdds, CallingStation, AllIn):
    total = sum(play_duplicate(cls(), cls(), d) for d in decks[:150])
    assert total == 0, (cls.__name__, total)
lad = lambda: Ladder("L", 0.4, 0.55, 0.65, 0.75)
assert sum(play_duplicate(lad(), lad(), d) for d in decks[:150]) == 0
print("mirror test ok")

# 3. Known result: AllIn vs CallingStation is pure card luck, so duplicate must cancel to 0.
assert sum(play_duplicate(AllIn(), CallingStation(), d) for d in decks) == 0
print("all-in vs station cancels ok")

# 4. Every bot can play every other bot without crashing.
bots = dev_roster() + holdout_roster()
for b in bots:
    for o in (AllIn(), CallingStation(), PotOdds()):
        for d in decks[:5]:
            play_duplicate(b, o, d)
print(f"all {len(bots)} bots run ok")
