# Journal

Research log for this project: every step, result, decision and mistake, in order.
New entries go at the bottom. Mistakes are corrected in later entries, not by rewriting earlier ones.

---

## 2026-10-31 - Setup

**Background**
- In Year 11 Specialist Maths I did an assignment on combinations and permutations of poker hands:
  how likely each hand is and which beats which. This project automates that maths and puts it
  inside bots that actually play.
- Inspiration: a bot competition where the winner just went all-in every hand and everyone else
  folded. That is an exploitative strategy (beats scared opponents, loses to anyone who calls
  correctly), and testing that idea is part of this project.

**Design**
- Game: heads-up No-Limit Texas Hold'em, blinds 50/100, 200 big blinds deep, stacks reset every
  hand (same format as Slumbot and the old Annual Computer Poker Competition).
- Rules engine: PokerKit (open-source library) handles dealing, betting rules and showdowns.
- Equity: preflop table for all 169 starting hands (simulated, 40k runs each); postflop Monte Carlo
  (400 runs); river exact. Checked against known numbers: AA 85.4%, KK 82.3%, AKs 67.1%, 72o 34.8%
  vs a random hand. (The worst hand heads-up is 32o at 32.3%, not 72o.)
- Duplicate dealing: every deck is played twice with the bots swapping seats, and every match uses
  the same decks. Luck mostly cancels. Tests confirm a bot vs itself nets exactly 0.

**Validation plan (fixed before seeing any results)**
- Development: 20 bots, full round-robin, 3000 decks (6000 hands) per match.
- Selection rule: the champion is the bot with the highest average bb/100 across its 19 opponents,
  each opponent weighted equally. No re-tuning of any bot after seeing results.
- Choosing the best of 20 is a parameter search, so its round-robin score is biased upward.
- Holdout: 8 fresh opponents (holdout_bots.py), written before any results and frozen. Built
  differently on purpose: chart-based preflop, check-raising, polarised overbets, probe bets,
  random thresholds. Run once, on the champion and all other dev bots for comparison.
- Pass condition: the champion is profitable on average against the holdout bots, beats at least
  6 of 8, and ranks in the top 3 of the dev bots on the holdout.
- Final exam after that: Slumbot (a strong public heads-up bot).

## 2026-10-31 - Development round-robin (20 bots, 6000 hands per match)

| Rank | Bot | Avg bb/100 | Beats | Worst result |
|---|---|---|---|---|
| 1 | Trapper | +897 | 17/19 | -168 |
| 2 | Ladder_Tight | +623 | 14/19 | -409 |
| 3 | Ladder_BigSizes | +565 | 12/19 | -474 |
| 4 | PotOddsRange | +553 | 18/19 | -180 |
| 5 | Exploiter | +517 | 15/19 | -196 |
| 10 | Rock | +274 | 18/19 | -11 |
| 17 | AllIn | -835 | 1/19 | |
| 20 | Maniac | -2159 | 1/19 | |

Full table: results/dev_roundrobin.txt. Typical 95% interval on a single match: about +/-70 to 170 bb/100.

**Findings**
- Champion by the fixed rule: Trapper (checks/calls hands with over 80% equity until the river, then
  shoves; otherwise plays pot odds).
- The all-in bot from the competition story finished 17th. It only beats bots that fold too much;
  any bot with a proper calling rule beats it.
- Most of Trapper's lead comes from farming the four weakest bots (+3672 vs Maniac, +3505 vs
  CallingStation). Head to head with strong bots it's ordinary: it loses to PotOddsRange (-168) and
  is level with Rock and Exploiter. Excluding the five weakest bots, Trapper (+363) and PotOddsRange
  (+346) are nearly tied.
- Rock is the most robust bot (beats 18/19, worst -11) but ranks 10th on average because it doesn't
  exploit weak opponents. The averaging rule rewards exploitation, so I noted it but did not change it
  after seeing results.

## 2026-10-31 - Holdout (run once)

| Rank | Bot | Avg bb/100 | Beats |
|---|---|---|---|
| 1 | Trapper | +635 | 7/8 |
| 2 | Ladder_BigSizes | +505 | 5/8 |
| 3 | Ladder_Default | +497 | 5/8 |
| 4 | Ladder_Tight | +475 | 7/8 |
| 7 | PotOddsRange | +113 | 5/8 |
| 8 | Rock | +65 | 4/8 |
| 19 | AllIn | -708 | 0/8 |

**Verdict: Trapper passes all three pre-set conditions** (profitable on average, beats 7 of 8, ranks 1st).

**Caveats**
- The holdout field is also rule-based and soft. Trapper's biggest wins are vs StickyCaller (+1981)
  and Limper (+1039); excluding StickyCaller its average is +442, still first.
- Its one loss is vs NitShover (-216 +/- 77): it calls tight shoves using equity vs a random hand,
  which overrates its hand against a range that only shoves the top 5%. This is a known weakness. I
  won't fix it now, because fixing it after seeing the holdout would be tuning on the holdout.
- Ladder_Tight (my equity-threshold ladder idea, with tighter thresholds) is the most consistent
  ladder: 7/8 on the holdout.
- All bots share the same equity engine, so the dev and holdout fields aren't fully independent.
  Slumbot, which plays near-equilibrium poker, is the real test, and I expect most of these bots to
  lose to it.
- Variant count: 20 dev bots. The holdout is now spent.

## 2026-10-31 - 6-max setup (fixed before results)

**Why**: most real poker is 5-6 players, and the heads-up winner might not transfer.

**Changes**
- New engine (engine_multi.py): N players, blinds 50/100, 100bb deep (standard online 6-max).
  Each deck is played 6 times with the bots rotated through every seat, so each bot gets every
  seat's cards and position once. Tests: zero-sum, and 6 copies of one bot net exactly 0.
- Multiway equity: chance of winning against everyone still in the hand (AA vs 5 random hands is
  48.6%, matching published figures).
- Threshold calibration: the bots' thresholds were written for heads-up, where AA is 85%.
  Multiway, each bot's strength number is converted to the heads-up scale by percentile (top 10%
  six-handed = top 10% heads-up). Pot-odds calls use the true multiway probability.
  Approximation: the map is built from preflop hands and applied postflop too.
- These edits touched bots.py and the frozen holdout_bots.py. Heads-up behaviour is provably
  unchanged: re-running 4 heads-up matches gave identical chip results deck by deck.
- Exploiter pools its stats across all opponents at the table (it was built for one opponent).

**Plan**
- Pool: all 28 bots (20 dev + 8 holdout; the holdout is already spent, so it just adds variety).
- Tables: 6 bots drawn at random, 30 decks x 6 rotations = 180 hands per table.
- Sample A: 600 random tables. Sample B: 600 new tables, different line-ups and decks.
- Rule: 6-max champion = highest average bb/100 in A. Confirmed if it is profitable and top 3 in B.
  Also report the A-vs-B rank correlation (how repeatable the rankings are).
- No bot is changed after seeing results.

## 2026-10-31 - 6-max results

Sample A and B: 600 tables each, 108,000 hands each. Full table: results/multi6_AB.txt.

| Bot | A bb/100 | A rank | B bb/100 | B rank |
|---|---|---|---|---|
| PushFold | +690 | 1 | +559 | 1 |
| Ladder_Tight | +521 | 2 | +382 | 5 |
| TAG | +518 | 3 | +389 | 4 |
| H_RangeReg | +487 | 4 | +530 | 2 |
| LAG | +481 | 5 | +410 | 3 |
| Rock | +390 | 6 | +339 | 8 |
| Trapper | +304 | 9 | +337 | 9 |
| PotOddsRange | +252 | 14 | +343 | 7 |
| AllIn | -745 | 24 | -786 | 24 |
| CallingStation | -2005 | 28 | -1757 | 28 |

**Verdict: PushFold is the 6-max champion and is confirmed on B** (profitable, ranked 1st).
Rankings are very repeatable: A-vs-B rank correlation 0.93.

**Findings**
- The heads-up champion doesn't transfer: Trapper drops to 9th. Slow-playing gives free cards to
  several opponents at once, which costs far more multiway.
- Preflop hand selection matters more 6-handed: the tight, chart-like bots (TAG, RangeReg, Rock)
  move up.
- Diagnostic only (decided after seeing results, so not a selection test): on the 122 "tough"
  tables with none of the 8 losing bots, the ladders collapse (Ladder_Tight -69, Ladder_Default -290).
  Their profits came from weak tables. PushFold (+255 +/- 144), PotOddsRange (+203), NitShover (+201)
  and Exploiter (+184) lead. Results in results/multi6_tough_tables.txt.

**Caveats**
- PushFold shoves 100bb with the top 30% of hands. It wins because these bots call shoves using
  equity vs a random hand, which overrates their hands against a 30% range. A competent opponent
  calls tighter, and PushFold would bleed. It's the competition all-in story in a milder form:
  exploiting a flaw every bot here shares.
- That shared flaw (judging calls vs a random hand instead of the bettor's likely range) is the
  biggest weakness in the roster. It also caused Trapper's holdout loss to NitShover.
- Every bot uses the same equity engine, so all of these results measure exploitation of a related
  field.

## Overall assessment (opinion, not a pre-registered test)
- Tournament winners: Trapper (heads-up, passed holdout) and PushFold (6-max, confirmed on B). Both
  won mainly by exploiting soft bots.
- Most robust against stronger opposition: PotOddsRange. It beat Trapper head to head, was 2nd on
  the tough 6-max tables, and is the only bot that discounts its equity when facing a bet. Picking it
  is a post-hoc judgement made after seeing results, so it carries selection bias.
- Next: Slumbot. Test Trapper (pre-registered champion) and PotOddsRange (judgement pick), and
  report both.

## 2026-11-09 - Slumbot test setup (fixed before any hands are played)

**Client** (slumbot_client.py): replays Slumbot's action string into PokerKit, builds the same
observation the tournament engine uses, and sends the bot's decision back. Offline test
(test_slumbot_client.py): a mock server speaking Slumbot's format, with our bots in Slumbot's seat,
gave exactly the same chips as the tournament engine on all 4,800 test hands (2 heroes x 8
opponents x 300 hands, including all-in and fold-preflop cases).

**Plan**
- Bots: Trapper (heads-up champion by the pre-set rule) and PotOddsRange (judgement pick, chosen
  after seeing results). Both are tested and both are reported.
- 5,000 hands each. Metric: bb/100 with 95% interval, plus splits by position and showdown/fold.
- No bot is changed before or during the run.
- No duplicate dealing is possible against Slumbot, so variance is much higher than in our
  tournaments. Trapper's spread in a mock run implies about +/-160 bb/100 at 5,000 hands. That's
  enough to tell a big loss from break-even, but probably not enough to separate the two bots
  unless the gap exceeds about 230 bb/100.
- Expectation: both lose. Slumbot plays near-equilibrium and should call big bets correctly.

## 2026-11-09 - Trial run; plan amended before the main run

- A 10-hand trial run of Trapper against the real API: -47 bb/100 (meaningless, noted for
  completeness). Those hands were discarded, and the main run starts from zero.
- The real API also returns `baseline_winnings`: what Slumbot would have won in our seat with the
  same cards. winnings minus baseline cancels most of the card luck, like our duplicate dealing.
- Amendment, made before any main-run hands: the primary metric is now baseline-adjusted bb/100.
  Raw bb/100 is still reported, and the baseline is saved for every hand.

## 2026-11-15 - Slumbot results (5,000 hands each)

Both runs completed: 5,000 hands per bot, no gaps.

| Bot | Raw bb/100 (main result) | All-in EV bb/100 | Slumbot baseline (should be ~0) |
|---|---|---|---|
| Trapper | -128 +/- 74 | -146 +/- 71 | -154 +/- 73 |
| PotOddsRange | -60 +/- 70 | -64 +/- 65 | -90 +/- 69 |

**Correction to the earlier amendment.** The baseline-adjusted metric I made primary on 2026-11-09
is invalid. Slumbot's baseline averaged -154 and -90 bb/100 when it should average about zero (2 to 4
standard errors off in both runs). Other people's Slumbot benchmarks found the same thing: one
measured a clearly non-zero baseline mean, and another found a random-action bot scored +125 bb/100
once the baseline was subtracted. Subtracting a biased baseline inflates the result by about
90-150 bb/100. The mid-run "roughly break-even" read was based on it and was wrong.
The main result goes back to raw bb/100, as originally planned.
All-in EV was added after seeing the data. It's a standard, unbiased adjustment (it replaces the
luck of the remaining cards after a pre-river all-in with the hand's equity), but only 10 and 21
hands qualified, so it barely narrows the intervals. It doesn't change any conclusion.

**Findings**
- Trapper loses clearly: -128 bb/100, and the interval excludes zero. It won 22 and lost 60 of the
  pots of 100bb or more. Shoving the river with any hand that has over 80% equity vs a random hand
  gets called mostly by better hands. Its leak is in the big blind (-270 vs -22 on the button).
- PotOddsRange: -60 bb/100. It probably loses, but the interval (about -130 to +10) includes zero.
  Its result is balanced across positions.
- The two bots aren't statistically different: the gap of 68 bb/100 has an interval of +/- 102.
- Slumbot folded to us often (Trapper won 1,944 hands without showdown). The losses come from the
  hands that go to showdown.
- Context: a CFR-trained bot in another public benchmark lost about 22 bb/100 to Slumbot. Simple
  rule-based bots losing 60-130 bb/100 is in line with expectations.

**Verdict on the project's question**
- The heads-up champion (Trapper) does not hold up against a strong opponent. It beat our field by
  exploiting weak bots.
- The judgement pick (PotOddsRange) did better, but not significantly so.
- The only bot that thinks about the bettor's range is the one that held up best, in every test.
  That points to v2: range-aware calling and value-betting, with fresh holdout bots and Slumbot as
  the test.
