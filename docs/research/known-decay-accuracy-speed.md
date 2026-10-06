# Research note: what Known means — evidence decay, the accuracy bar, a speed term, and early presses

> **Status:** Findings and a proposal, written before the decisions. The developer has since decided each question; what was decided, and where it differs from the proposal, is in [§ Proposal, and what was decided](#proposal-and-what-was-decided). The ADRs carry the decisions.
> **Date:** 2026-10-04 (alpha-plan #12f)
> **Feeds:** [ADR-027](../adr/0027-key-and-accuracy-state-model.md) (Known), [ADR-024](../adr/0024-drill-content-and-lesson-granularity.md) (need, Phase C), [ADR-011](../adr/0011-persistence-and-state.md) (`latency_ms`)
> **Sources:** listed at the end with how each was read; PDFs are in the gitignored `docs/research/references/`

**One-line summary:** The literature supports the direction of all four ideas and gives the
parameter for none of them. Forgetting of a motor skill runs on months and shows first in accuracy;
learning runs over days to weeks of practice and shows in speed, so decay is one long half-life and
the learning side is carried by practice days and latency; the published accuracy
figures the row compared against are *after correction*, so Takki's first-press 90% is not as low
as it looked; a speed term is well grounded as a measurement of location memory but not as a
cause of retention; and an early press can be kept as a negative latency, but a ratio cannot be
taken on signed numbers, and the 10-second re-prompt currently hides the slowest answers.

---

## How to read this note

Every claim is tagged with how its source was read:

- **[full]** the paper or page itself was read, and figures are quoted from it.
- **[abstract]** only the abstract or the author's own summary was read.
- **[cited]** known only through another paper that cites it. Not verified.
- **[own]** this note's own arithmetic or reasoning, not a finding from the literature.

Nothing here is specific to blind children or to children learning to type. No such study was
found for any of the four questions. Every source is applied by analogy, as ADR-024's research
grounding already says of its own.

## Corrections to the row's first-pass survey

The #12f row listed figures from secondary sources. This is what the primaries say.

| Row's claim | What the primary says |
|---|---|
| "Physical skills decay far slower than cognitive ones" (Arthur et al. 1998) | Smaller, not far smaller: δ = −0.75 for physical against −1.15 for cognitive tasks, collapsed across all retention intervals **[full]**. The same table shows **accuracy** measures decaying three times more than **speed** measures (δ = −1.00 against −0.32), and Takki's measure is accuracy. Arthur is also superseded: see Tatel & Ackerman 2025 below. |
| "Real typists leave ~1.2% of keystrokes uncorrected" (Dhakal et al. 2018) | Correct, 1.17% (SD 1.43) **[full]**, but it is the error rate **after backspacing**. The same typists spent 6.3% of their keypresses on Backspace or Delete. It is not a first-press figure. |
| "Skilled transcription error rates typically 1–3%" (Salthouse 1986) | **Not verified.** The paper could not be obtained. |
| "Civil-service tests 95% at 40 WPM over 5 min (UK, Australia)" | **No primary found** for either country. The one government standard found is the US one: 40 words per minute, "based on a 5 minute sample with three or fewer errors" (OPM) **[full]**. Three errors in about 1,000 keystrokes is 99.7%, again after correction. |
| "Admin/data-entry/legal roles 96–99% at 55–80 WPM" | **No primary found.** These come from typing-test vendors' pages. Dropped. |
| "School goals 90–100% at 20–25 WPM in grades 3–4, 95% at 25 WPM by end of elementary" | The one state page read (Wisconsin DPI) gives a speed rule, 5 WPM × grade, and **no accuracy figure** **[full]**. The 85–95% accuracy figures are from district and vendor pages. No state standard stating an accuracy percentage was found. |
| "APH Talking Typer defaults to 95% and 25 WPM" | Confirmed from APH's manual **[full]**. The manual does not say how accuracy is counted. |
| "keybr unlocks on per-key speed alone" | Confirmed from its source: the next letter is included when every included key's *confidence* (speed against the target) is at least 1. Accuracy is not in the rule **[full]**. |
| "Fuller & Fienup 2018 and replications find higher criteria (90%, 100%) maintain better than 80%" | Fuller & Fienup compared **50%, 80% and 90%**, not 100%, with three children **[full]**. The 100% result is Richling et al. 2019 **[abstract]**. Details below. |
| "Settles & Meeder 2016 is the nearest precedent" | It is the precedent for a half-life that grows with practice. It models *the chance of recalling a word*, not *how much old evidence is worth*. The nearer precedent for "uncertainty widens with time" is the Glicko rating system. Both below. |
| "The typing-relearning savings literature, source to be found" | Found, not obtainable. Hill, Rejall & Thorndike 1913 and Hill 1934, 1957 are the classic typing studies; all paywalled, and a 1979 US Army report on typewriting retention and relearning (DTIC ADA072369) refused the download. Known here only as cited. |

---

## 1. Evidence decay

### What the sources say

**Skill decay runs on months, and accuracy goes before speed.** Tatel & Ackerman (2025,
*Psychological Bulletin*) is the current meta-analysis: 1,344 effect sizes from 457 reports, all
procedural skills with a motor component, **adults only** (17 and over) **[full, accepted
manuscript]**. Performance fell by 0.08 SD per month of non-use for accuracy measures and 0.06
for speed. Half of what training had gained was lost after about **6.5 months for accuracy** and
**13 months for speed**. They fitted a straight line and say plainly that it is wrong at long
intervals (it predicts falling below the untrained level). They also note that in Arthur et al.'s
data 51% of the data points had a retention interval of seven days or less.

Arthur et al. (1998, 53 articles, 189 data points, 178 after outliers were removed) by interval,
read from the paper's Table 3 **[full]**: about zero under a day; δ = −1.01 at 1–7 days (89 of the 178 data points); −1.52 at
8–14 days; −0.93 at 15–28; −0.65 at 29–90; −1.39 at 91–180; −1.03 at 181–365; −1.27 beyond a year.
That is not a smooth curve, and half of it is one bucket. It supports "there is loss, and more of
it later" and nothing finer.

**The one typing study with retention data.** Baddeley & Longman (1978) retested 55 postal workers
1, 3 or 9 months after 60–80 hours of keyboard training **[full]**. Speed loss was "approximately
30% after 9 months" and "does not increase substantially after the first three months"; error rate
rose but "for most subjects it remains within reasonable limits". These were adults with tens of
hours of practice.

**How well a skill was consolidated decides how long it lasts.** Already in this repository
(Danna et al., [motor-learning-repetitions.md](motor-learning-repetitions.md), **[abstract]**):
7–8 year olds given 90 repetitions in one sitting kept nothing at 4–5 weeks, and those given the
same letter over four days were still improving at 4–5 weeks. That is the only children's evidence
in this note, and it is the strongest argument against one half-life for every key.

**A half-life that grows with practice is the standard form.** Settles & Meeder (2016) **[full]**
model recall as `p = 2^(−Δ/h)`, with Δ the time since last practice and h the half-life, and
estimate `h = 2^(Θ·x)` where x counts how often the learner has seen the item, got it right and got
it wrong. Half-life therefore grows exponentially with successful exposures ("a common practice in
spacing and lag effect research"). They show that Leitner boxes and Pimsleur's schedule are special
cases with fixed weights (Leitner: double on a correct answer, halve on a wrong one). On 13 million
Duolingo traces it cut prediction error against Leitner from 0.235 to 0.128. Its domain is adult
vocabulary recall, which is declarative memory, and its half-lives were fitted to data Takki does
not have.

**Widening uncertainty with time, without moving the estimate, also has a precedent.** In
Glickman's Glicko system **[full, the author's description; the 1999 paper not read]** "a player's
rating changes only from game outcomes, but his/her RD changes both from game outcomes and also
from the passage of time when not playing": `RD = min(√(RD² + c²t), 350)`. The rating is the
estimate, RD its uncertainty. This is the developer's idea in another field: time does not say the
child got worse, it says Takki knows less.

**Spacing.** Cepeda et al. (2008) **[abstract]**: with 1,350 people, the best gap between two study
sessions was about 20% of the delay to the test for delays of a few weeks, falling to about 5% at
a year. It says when a refresher is most useful, not how fast evidence ages. Cepeda et al. 2006 was
not read.

### What the sources do not say

- No half-life for a child's memory of a key position, or for any motor skill in children.
- Nothing on blind learners.
- Nothing on down-weighting old evidence as such. That is a statistical device chosen here; the
  literature supplies only the reason for it.
- Hill's typing relearning figures (how much faster relearning was after 25 and 50 years) could
  not be read.

### What follows for the design **[own]**

Decay can only bite the part of Known that is an *estimate*. Known has three parts and they are
different kinds of thing:

- the **90-press floor** is a dose (Danna's repetitions). The child did press the key 90 times;
  time does not undo that;
- the **two practice days** are a fact about the calendar;
- the **accuracy** is an estimate, and an old estimate is worth less.

So the weights go into the accuracy bound that #12e's need already uses, and nowhere else. With
each press weighted `2^(−age / h)`, the effective sample shrinks with time, the lower bound falls,
and need rises with no timer.

How long that takes is fixed by arithmetic, not by taste. At `CONFIDENCE_Z = 1` the lower bound on
an all-correct history of n effective presses is `n / (n + 1)`, so it stays above 0.90 until fewer
than about 9 effective presses are left:

| Key's window | Bar | Idle time before the bound falls under the bar |
|---|---|---|
| 90 presses, 94.4% (only just Known under a bound, § 2) | 0.90 | 1.0 half-life |
| 150 presses, 96% | 0.90 | 2.6 half-lives |
| 200 presses, 98% | 0.90 | 3.9 half-lives |
| 200 presses, 100% | 0.90 | 4.5 half-lives |
| 200 presses, 100% | 0.95 | 3.4 half-lives |

Three consequences:

1. **A well-practised key waits three to four half-lives before it asks for anything.** The
   half-life must be chosen with that multiplier in mind. A 30-day half-life would leave a strong
   key unquestioned for four months.
2. **Restoring is cheap.** A key that has just dropped under its bar comes back with one or two
   correct presses; one whose evidence has gone completely needs about 10 in a row at 0.90 and 19
   at 0.95. This is the "few correct presses on return" the developer described.
3. **Decay cannot replace #12g's second-day rule.** ADR-024 says it will. It will not: a key with
   90 correct presses on its first day has zero need until its evidence has aged 3.3 half-lives,
   so the next morning it is still not planned. The rule "a missing day is a need of one press"
   has to stay.

---

## 1b. Learning, as distinct from retention

*(Added 2026-10-04, after the developer pointed out that § 1 is all about retention and rests its
one claim about learning on a single paper. It was right to ask: the acquisition literature is
large, and it changes the proposal for § 1.)*

### What the sources say

**Learning has a fast part and a slow part, and the slow part takes weeks.** Karni et al. (1998,
*PNAS*) **[full]**: adults practised a finger-opposition sequence 10–20 minutes a day for about
five weeks. Speed went from 17.4 to 38.4 sequences per 30 seconds and errors from 2.4 to 0.5, and
performance "neared asymptote after about 3 weeks of training". They describe three stages: fast
learning within a session, a consolidation period of some 6–8 hours after it during which further
gains appear with no practice, and slow learning, "delayed, incremental gains" over weeks of
continued practice. The skill was specific to the trained sequence and was still there a year
later.

**In children's typing the slow part had not finished after 10,000 to 20,000 keystrokes.** Van den
Bergh et al. (2015) **[full]** is the one study found of children learning to type: 62 children,
mean age 12.6, on a Dutch online course, 1.09 million keystroke latencies, home row only. On
average the time between keystrokes was still falling at the end: "on average the children had not
finished developing their skills". Only the easiest transitions (the same finger twice) levelled
off, and only in about half the children. Two limits: these were sighted children chosen from the
top quarter of the course, and only correct keystrokes were analysed, so it says nothing about
accuracy.

**What a child gains in one session is kept for weeks.** This is where § 1's reading of Danna was
too narrow.

- Dorfberger, Adi-Japha & Karni (2007) **[full]**: 9-, 12- and 17-year-olds, about 20 in each
  group, one session of 20 thirty-second blocks. All three groups were faster 24 hours later with
  no further practice, and "the gains attained by the 48 hours post-training test were completely
  retained over an interval of 6 weeks, with no additional training". The 9- and 12-year-olds kept
  their gains even when a competing sequence was trained two hours later; the 17-year-olds did not.
- Julius & Adi-Japha (2015) **[full]**: children of 5–6 and 7–8 and adults, one session of a
  letter-like pen task. All groups were faster at 24 hours and held that speed at two weeks.
- Adi-Japha et al. (2019) **[full]**: 5-year-olds were faster two to four hours after training and
  kept it at two weeks; adults showed no gain until the two-week test.
- Van Roy et al. (2026) **[full]**: children of 7–11 gained more than adults, in speed and in
  accuracy, over five waking hours after practice. It repeats their own 2024 result.

Against these stands Danna's finding that 90 repetitions in one sitting left no gain at 4–5 weeks
while 180 did. Read together: **a sufficient single-session dose is retained by children for
weeks**, and children stabilise what they learned faster than adults, not slower.

**Learning shows in speed. Accuracy is high early and stays flat.** In Julius & Adi-Japha accuracy
was 85%, 87% and 95% for the three age groups "throughout the experiment" while speed improved; in
Adi-Japha et al. accuracy did not change between sessions; van den Bergh's learning curves are
latency curves. Karni's errors did fall, from an already low rate.

**Sleep is not established as the cause.** Pan & Rickard (2015, *Psychological Bulletin*)
**[abstract]** reviewed the sleep and motor-learning literature and concluded that sleep does not
enhance motor learning, and that much of the reported overnight gain comes from how the data were
averaged and from fatigue at the end of training. The children's gains above appeared within hours
of waking time. Savion-Lemieux & Penhune (2005) **[abstract]** found an optimal number of trials
per day beyond which more practice that day added little.

### What the sources do not say

- How many days a child needs before a key position is learned. Karni's three weeks are adults on
  one sequence; van den Bergh's children were still improving on eight keys when the data ended.
- Anything about accuracy as a learning curve in typing.
- Nothing here is about blind children.

### What follows for the design **[own]**

1. **Learning and forgetting are two processes on two clocks, and decay models only the second.**
   Learning runs over days to weeks of repeated practice and shows in speed. Forgetting runs over
   months and shows first in accuracy (§ 1). A half-life that is short for a young key and long
   for an old one tried to make one mechanism do both jobs.
2. **There is no evidence that a young key is forgotten quickly.** § 1 proposed half-lives of one
   and two days for a key practised on one or two days, from Danna alone. The four children's
   studies above say the opposite: one session's gain lasts two to six weeks. What a young key
   lacks is not fresh evidence but *more days of practice*, and Takki already expresses that
   directly, through the practice-day floor and #12g's second-day rule.
3. **So the half-life should be one value, on the scale of months.** Because a strong key keeps
   its bound for three to four half-lives (§ 1's table), a half-life of about 30 days means a key
   that is only just Known is asked for again after a month away, and a strong one after about
   four months. That sits inside what Tatel & Ackerman and Baddeley & Longman report.
4. **Accuracy saturates before learning is over.** If learning shows in speed, a key can reach
   90% on its second day and still be weeks from fluent. Known on accuracy alone certifies the
   early part of learning. This is the strongest argument in this note for § 3's speed term: it
   is the only measure Takki has that keeps moving while a key is being learned.
5. **The two-day floor rests on practising across days, not on sleep.** ADR-027 gives sleep as
   the reason. The evidence for spreading practice over days is good (Karni, Danna, Baddeley &
   Longman); the evidence that sleep is the mechanism is disputed. The rule stands; its stated
   reason is weaker than the ADR says. Whether two days is enough is not answered by anything
   found: the acquisition studies suggest learning continues well past it.

---

## 2. The accuracy bar

### What the sources say

**The published accuracy figures are measured after correction.** Dhakal et al. (2018) **[full]**:
168,960 volunteers, mean age 24.5, 72% had taken a typing course, mean 52 WPM. Uncorrected error
1.17%. But 6.3% of all keypresses were Backspace or Delete, 2.3 corrections per sentence, and in a
783-person subsample analysed keystroke by keystroke the rates were 1.65% substitutions, 0.80%
omissions and 0.67% insertions. Slow typists (under about 26 WPM) left 1.78% uncorrected, spent
9.05% of keypresses correcting, and made 3.72% substitutions. Baddeley & Longman's trainees after
60 hours left 1.09–2.06% uncorrected and corrected a further 0.5% or so.

Takki has no backspace (ADR-012) and counts the first press only. **[own]** The comparable adult
figure is therefore the error rate *before* correction, which these numbers put at roughly 2–7% of
keystrokes: a first-press accuracy of about 93–98% for practised adults typing continuous text.
The row's conclusion that 90% is low and 95% modest rested on the after-correction figures. Takki's
task is still easier per press (one spoken letter, no time pressure, a small set of keys), and its
learners are beginners and children. The honest reading is that **0.90 and 0.95 are in the range
of real first-press performance, neither clearly low nor clearly strict**.

**Mastery criteria: what is maintained tracks the criterion.** Fuller & Fienup (2018) **[full]**:
three boys aged 5–7 with autism, sight words and spelling, criteria of 50%, 80% and 90% in one
session, probed weekly for 3–4 weeks. Maintenance averaged 68 / 88 / 93% for one child, 35 / 58 /
83% for the second, 60 / 60 / 90% for the third. Richling, Williams & Carr (2019) **[abstract]**:
four participants, criteria across three sessions; only the 100% condition stayed above 80% at
follow-up, and 80% across three sessions "may be insufficient". McDougale et al. (2019) **[full]**
reviewed practice and research: 52% of clinicians use 80% across three sessions, 90% is the most
common figure in published studies, and "clinicians are commonly using mastery criteria that are
not empirically based". Wong et al. (2022) **[abstract]**: across the literature, higher criteria
go with better maintenance and generalisation.

These are small-n studies of children with developmental disabilities learning words, not keys.
What carries over is the shape: performance later sits at or a little below the level demanded at
mastery, so the criterion should sit above the level one wants kept.

**Products.** APH Talking Typer, made for blind students, advances a lesson at 95% and 25 WPM by
default, both adjustable **[full]**. keybr uses no accuracy test at all **[full]**. OPM's clerk
standard is 40 WPM with at most three errors in five minutes **[full]**.

### What the sources do not say

No study gives an accuracy criterion for a single-key, untimed, first-press task, for children, or
for blind learners. There is no evidence for moving 0.90 to any other particular number.

### What follows for the design **[own]**

The firmer finding is statistical, and it is about Known as written. Known's test is a raw
proportion: 81 correct of 90. The lower bound on that (Wilson, z = 1, the measure #12e's need
uses) is **0.864**. Known certifies "probably above 86%", while the planner works toward "surely
above 90%". That is the disagreement ADR-024 lists under known costs.

If Known's accuracy test becomes *the lower bound reaches the bar*, the nominal bars can stay
where they are and the test gets stricter exactly where the evidence is thin:

| Window | Correct presses needed for a bound of 0.90 | For 0.95 |
|---|---|---|
| 25 | 25 (100%) | 25 (100%) |
| 50 | 48 (96.0%) | 50 (100%) |
| 90 | 84 (93.3%) | 88 (97.8%) |
| 150 | 139 (92.7%) | 146 (97.3%) |
| 200 | 185 (92.5%) | 194 (97.0%) |

That is an effective raise from 90% to about 93% for Known, in line with the mastery literature's
direction, without picking a new number the evidence does not supply.

The anchor rung is where this is felt. Today 24 of 25 passes. Under a bound at 0.95 it takes 19
presses with no miss, 52 with one, 79 with two. The planner has held the six Stage 0 keys to that
bound since #12e, so the rung would follow what is already practised, but it is a real tightening
and should be heard in #12h.

The 90-press floor does not give way to the bound. They stop answering the same question: the
floor is the dose, the bound is the accuracy.

---

## 3. A speed term

### What the sources say

**Skilled typists know where the keys are without being able to say so.** Snyder et al. (2014)
**[abstract; the figures are from summaries of it and were not checked against the paper]**:
skilled typists placed letters on a blank keyboard correctly about 57% of the time, yet typed at
about 94% accuracy. Key location in a fluent typist is procedural memory. That is the memory Takki
is trying to build, and it is exactly what a child who feels across the keys does not have while
still pressing the right one. Accuracy cannot tell the two apart; time can.

**Speed and accuracy decay differently.** Tatel & Ackerman: half of the gain lost at 6.5 months
for accuracy, 13 months for speed. Arthur et al.: δ = −1.00 against −0.32. Tatel & Ackerman also
warn that retention results are confounded by speed–accuracy trade-offs unless both are measured.

**Requiring speed is common practice with thin causal evidence.** Every product and job standard
above pairs accuracy with speed except keybr, which uses speed alone. Doughty, Chase & O'Shields
(2004) **[abstract]** reviewed the fluency literature and found "sparse" evidence that building
rate produces better retention once the amount of practice is controlled.

**How to summarise latencies.** Whelan (2008) **[full]**: the median is the usual robust summary,
but it is a biased estimator on skewed data, the bias grows as the sample shrinks, and so "the
median should never be used on RT data to compare conditions with different numbers of trials".
Reaction times under 100 ms are not genuine and are "normally eliminated by using a cutoff of
between 100 ms and 200 ms".

### What the sources do not say

- No reaction-time norms for blind children at a keyboard, and no usable primary on children's
  choice reaction time to a spoken letter was obtained. The ADR's refusal of an absolute
  millisecond threshold stands.
- No study gives a ratio. `PHASE_C_MAX_LATENCY_RATIO = 1.5` and any figure proposed below are
  starting points.

### What follows for the design **[own]**

**A speed term is justified as a measurement, not as a training effect.** It answers "does this
child have a location memory for this key", which accuracy does not. It should not be argued as
"speed practice improves retention".

Four problems with the term as Phase C has it, each of which would matter more on Known:

1. **The baseline is circular.** It is the median over Known keys. The first keys become Known with
   no speed check (there is no baseline yet) and then *are* the baseline. A child who feels for
   every key sets a slow baseline, and every later key passes against it. A relative measure
   detects a key that is slower than the child's others. It cannot detect a child who searches for
   all of them.
2. **There is a baseline that is not circular: the two bump keys.** `f` and `j` are under the
   index fingers at rest and are found by touch. Answering them needs no search and no reach, so
   their latency is the child's own time to hear a letter and press, with location taken out. A
   reach key will always be somewhat slower (the finger has to travel), and a searched-for key
   much slower. This exists from the first day and is the same anchor ADR-027 already builds on.
   **Fingers are not equal, but the difference is small beside what the term looks for.**
   *(Added 2026-10-04, from the developer's objection, and revised the same day when the
   developer asked how large the difference is.)* What was found, all in adults:

   - Ekşioğlu & İşeri (2015) **[abstract]**, 148 people, all eight fingers, fast repeated
     tapping: index and middle fastest, little fingers slowest, and "all dominant-hand fingers,
     except little finger, had higher tapping rates than the fastest finger of the nondominant
     hand". So the hand matters about as much as the finger. The two extremes reported for men
     of 18–29 are 5.12 taps a second (right index) and 4.30 (left ring) **[from a summary of the
     paper's table, not checked]**: 16% in rate, about 40 ms per tap.
   - Aoki, Francis & Kinoshita (2003) **[abstract]**: the same order, index, middle, little,
     ring, with no figures in the abstract.
   - Lachnit & Pieper (1990) **[abstract]**: in a five-choice *reaction* task "thumb and little
     finger showed significantly shorter reaction times" than index, middle and ring. For one
     press in answer to a signal, which is Takki's case, the order is not even the same.
   - Nothing per finger was found for children.

   So the largest gap reported is some tens of milliseconds, or under a fifth, and for a single
   press its direction is not settled. A child who finds a key by feeling for it takes seconds
   longer, several times their ordinary answer. A ratio of 2.0 against the bump keys leaves room
   for a finger difference five times the largest one reported and still separates the two.

   **This makes the simple baseline the right one.** Two more careful baselines were considered
   and dropped. The same-finger *home-row* key assumes a home that only the index fingers have
   been given ([roadmap § D](../roadmap.md#d-smaller-gaps-worth-a-line-in-the-relevant-adr), "No
   finger but the two index fingers is ever given a home"), a home-row-first order that ADR-032
   keeps open, and a key that does not exist for the right little finger on a US keyboard, whose
   home cell is `;`. The fastest other key on the same finger avoids those but leaves each
   finger's fastest key measured against nothing. Both buy precision of tens of milliseconds
   inside a tolerance of hundreds. The median over `f` and `j` together also averages the two
   hands and the two kinds of letter name (§ 4). If pilot data shows a finger whose keys all sit
   near the ratio, the same-finger reference is the refinement to reach for.
3. **The medians are compared across unequal samples.** Phase C compares the last 30 presses of
   one key with every measured press of every Known key. By Whelan's rule both sides should be the
   same number of presses.
4. **The slowest answers are recorded as fast ones.** A prompt unanswered for
   `PROMPT_TIMEOUT_SECONDS` (10 s) is spoken again, and since #12j the answer is timed from the
   version heard last. A child who needs 12 seconds to find a key is recorded at about one second.
   No first press can record more than about 10 seconds, and the child the speed term exists to
   notice is the one it misses. #12j's rule is right for *reaction time to a letter just heard*;
   it is the speed term that needs to know the prompt had to be repeated.

**A gate needs a matching need.** If Known requires speed and the planner's need does not, a key
that is accurate and slow has zero need, is never targeted, never gets faster, never becomes Known
and holds its slot for good (#12g). Whatever Known tests, `presses_needed` must be able to see.

### The baseline pool: a spike **[own]**

*(Added 2026-10-04, after the decisions. The developer asked for recent presses on well-practised
keys to join `f` and `j`, and then for the candidate pools to be compared before one was built.)*

Once Known has a speed term, "the median over the Known keys" is circular. Three pools were
compared on fixed per-key medians, with keys meeting Known's floors in the English introduction
order (`f j`, `r u`, `v m`, `d k`, `s l`, `a`, …) and a key slow above 2.0 times its baseline. It
is a model of the rule, not a simulation of a child learning.

- **A:** `f`, `j` and every other key that meets the floors (dose, accuracy bound, days).
- **B:** `f`, `j` and the Known keys introduced earlier.
- **C:** `f`, `j` and every other Known key. Circular; solved by iteration from "nobody Known"
  it gave B's answer in every case, and from "everybody Known" it gave A's.

A and B agree on: an even child; a gradient between fingers (index 1,000 ms, middle 1,100, ring
1,250, little 1,450); each later step 9% slower than the one before (the last key 2.8 times `f`);
one hunted key at 2,600 ms, introduced early or late; three slow keys early; a weak right hand
(11 of 26 keys at 2,400 ms); and everything slow, `f` and `j` too. In all of these only the keys
past twice the others are held back, or none.

They differ when a group of keys is more than twice as slow as `f` and `j`:

| Case | A | B |
|---|---|---|
| `f j` at 650 ms, every other key at 1,400 (2.15 times) | `r u` held back while they are the only others; all Known from six keys on | every key but `f j` held back, at every stage |
| The first eight keys after `f j` at 2,400, later keys at 1,100 | all Known up to ten keys; all eight lose Known when the faster keys join | the eight held back from the start |
| Weak left hand (15 of 26 keys at 2,400) | held back until they are the majority, then all pass | held back throughout |

B makes `f` and `j` the yardstick for good, which is the finger and over-practice bias raised
above. A measures a key against the child's typical key, at the cost that a key's state can
change because of other keys and that a slower group passes once it is the majority. The slot
gate limits that: at most six keys can be short of Known, so the weak-left-hand flip at 26 keys
is not reachable. **The developer chose A**, and asked for the slower-group case, and the
left-hand and right-hand split in particular, to be looked at again for Beta (roadmap § D).

**A side finding, the same for both pools: a key near the bar flickers.** With 30 presses per key
and an assumed spread of 35% between presses, one evaluation calls a key slow this often:

| True ratio to the baseline | Pool `f j` only | Pool of 20 |
|---|---|---|
| 1.5 | 0.2% | 0.0% |
| 1.8 | 12.0% | 9.9% |
| 2.0 | 49.2% | 50.0% |
| 2.2 | 83.5% | 88.3% |

The size of the pool barely matters; the noise is in the key's own median. The 35% is an
assumption, not a measurement.

---

## 4. Early presses

### What the sources say

**A word is recognised before it ends.** Marslen-Wilson (1987) **[full]**: words heard in context
are selected about 200 ms after their onset, "well before the end of the word"; in Grosjean's
gating study listeners needed 199 ms of a word in context and **333 ms of the same word heard in
isolation**. A letter name spoken alone is the isolated case, and a closed set of a few letters is
easier than open vocabulary. So a fluent child pressing before a letter name has finished is
expected, not an artefact, and discarding those presses removes real answers.

**But not every early press is an answer.** Whelan (2008), after Luce (1986): a genuine reaction
takes at least 100 ms, and faster ones are treated as guesses and cut at 100–200 ms. Those are
figures for simple reactions measured from stimulus onset. For a choice among letters the child
must also hear enough of the letter to know which it is.

### Measured on Takki's own run **[own]**

*(Added 2026-10-04, when the developer asked what a ratio of 2.0 means in milliseconds.)* The
hands-on Windows run of 2026-09-26 logged every keypress against its letter's enqueue and finish
(`windows-validation-runs/2026-09-26/RS-22b-manual.log`): one sighted adult, SAPI, 262 first
presses, 258 correct, on the fixed ramp-up cycles that #12d has since replaced.

- **A letter takes 1.1 to 1.3 seconds** from enqueue to finish (median per letter, 1,140 ms for
  `a` to 1,297 ms for `h`).
- **The presses fall into two groups with nothing between them.** 64 came between 170 and
  454 ms after the enqueue, 198 came at 719 ms or later, and none in between. The first group is
  too early to be an answer to the letter: SAPI needs 100–150 ms to start, and the earliest of
  the second group is 61% of the way through its letter. These are presses made from the pattern
  of the old fixed cycle, not from hearing. 25 of the 64 were on `f` or `j` (of 42 presses on
  those two keys), 39 on the other six keys (of 220). *(The developer's point: they are a pattern
  match, not a hearing match, and have to be taken out before anything is read from the rest.)*
- **Of the 198 heard answers, the median came 1,125 ms after the enqueue, and 60% came before
  the letter's usual end.** Under today's rule those are unmeasured: 80 presses were timed.
- What a ratio of 2.0 allows depends entirely on where the time is counted from:

  | Timed from | Median | Bar at 2.0 | Room above the median |
  |---|---|---|---|
  | The end of the letter (today's rule, 80 presses) | 204 ms | 407 ms | about 200 ms |
  | The enqueue (198 heard answers) | 1,125 ms | 2,250 ms | about 1,125 ms |
  | Signed, from the letter's usual end (198) | −79 ms | no meaning | none |

- **With the pattern presses removed, `f` and `j` are not faster than the other keys.** Their
  median is 1,329 ms (17 presses) against 1,109 ms for the other six (181). Per key the medians
  run from 984 ms (`h`) to 1,516 ms (`f`). Seventeen presses are too few to read a difference
  from. Left in, the pattern presses put the `f`/`j` median at 273 ms, a baseline every other key
  would have failed.

Four things follow. The early press is the adult's normal answer, not a rare one. The room a
ratio gives is one second or a fifth of a second depending on the origin, so § 3's ratio and this
section's origin are one decision. The floor is not a detail: without it the baseline keys, which
are the ones most easily answered without listening, set a bar nothing can meet. And the gap in
this run sits at about half a letter, far above the 100–200 ms the reaction-time literature uses,
because a spoken letter has to start and become recognisable before it can be answered. The room
also scales with the voice: a shorter letter gives a smaller median and less room.

### What the sources do not say

Nothing was found on reaction times to spoken letter names, in children or adults, or on where in
a letter name it becomes identifiable. The next point is this note's reasoning.

### What follows for the design **[own]**

**A signed latency keeps the early answers, and it is cheaper than the handover assumed.** The
handover asked how to learn when a letter *started*. It is not needed. The moment the letter is
expected to finish is the time it was enqueued plus that letter's usual enqueue-to-finish time,
and both are already observable in the core: the enqueue is the core's own call, and every
completed letter reports its finish. No start event, and no Windows-side change.

**Three things the signed latency does not fix:**

1. **A ratio cannot be taken on signed numbers.** The handover says a signed latency "works with a
   median and with a ratio against the child's own baseline". The median, yes. The ratio, no: with
   a baseline of −50 ms, 1.5 times the baseline is −75 ms, a *stricter* bar, and a baseline of zero
   allows nothing. A ratio needs a true zero. The natural one is the letter's expected start, which
   means keeping the letter's expected length beside the latency so that either origin can be
   computed.
2. **A letter that is always answered early never finishes, so its length is never learned.** A
   press cuts the letter (ADR-012). The child who is fastest on a key would be the one whose
   presses on it stay unmeasured. The length has to be learnable from somewhere else, or those
   presses stay NULL.
3. **Letter names do not become identifiable at the same point.** In English `f l m n s x` all
   begin with the same vowel ("eff", "ell", "em", …) and differ only at the end, while `b d j k p
   t v` and most others differ from their first sound. Timed from the end, the second group can be
   answered before the reference point and the first cannot. Timed from the start, it is the other
   way round. Which letters are confusable also depends on which are Active. So no single
   reference point makes two different letters comparable to within a letter's length (some
   300–500 ms). This limits how tight any cross-key ratio can be, and it is one more reason the
   Stage 0 home keys, one from each group, are a reasonable pair to average as a baseline.

**The floor.** A press too soon after the letter began is not a reaction to it. The literature's
cut is 100–200 ms from onset, which is for a simple signal. On Takki's own run (above) the
presses that were not answers ran up to 454 ms after the enqueue and the first real ones began at
719 ms, so a floor of 250 ms would have let through 49 of the 64. A fixed number of milliseconds
is also tied to one voice. The floor that fits this data and travels to another voice is a share
of the letter: **a press earlier than half the letter's usual length is not timed.** On this run
that drops exactly the 64 and keeps exactly the 198. It is one adult, one voice and one run, so
it is a starting value.

**The half-letter floor was withdrawn the same day, and why.** *(Added 2026-10-04, on the
developer's point.)* The gap in that run is a sighted adult's gap. The developer has heard blind
adults listen to recorded messages at two or three times normal speed and could not follow half
of it. Two findings agree with that, both taken from search summaries and **neither read in
full**: Dietrich, Hertrich & Ackermann (2013) report blind listeners following speech at up to
about 22 syllables a second, against about 8 for sighted listeners; and a study of congenitally
blind adults (not identified beyond the summary) reports a simple reaction to a sound of 0.21 s
against 0.32 s for sighted controls. A listener who follows 22 syllables a second needs roughly
50 ms of a letter name to know which it is. With a reaction of about 200 ms and SAPI's
100–150 ms to start, a real answer from a blind child could come 350–450 ms after the enqueue,
inside the band this run called pattern presses. A floor at half the letter would discard the real
answers of the children Takki is for.

What replaces it has two parts. A **physical floor of about 250 ms from the enqueue** (the
voice's start plus the fastest reaction to any sound), before which a press is not an attempt at
all. And for every later press, **correctness as the judge**: the drill content is shuffled so
that the next prompt cannot be predicted, so a press made without listening is a guess and is
usually wrong, and the speed term reads correct first presses only. This rests on the content
doing its job, which is not yet shown, so the progress dump reports first-press accuracy by when
the answer came.

**The two #12j cases.** A press during a *re-spoken* letter, and a press over the resume
announcement, are not reactions to a letter heard for the first time; the child has known the
target for seconds. A signed latency is defined for the first hearing of a prompt. These two stay
unmeasured.

---

## Proposal, and what was decided

One recommendation per question, as proposed. The reasoning is in the sections above. The
developer decided all of them on 2026-10-04; a note under an item says where the decision differs.

1. **Decay:** weight each press by `2^(−age / half-life)` inside the accuracy bound, and nowhere
   else. **One half-life for every key, about 30 days.** A key that is only just Known asks for
   re-confirmation after about a month idle, a strong one after about four months. Known and need
   read the same decayed bound. #12g's second-day rule stays. *(Revised the same day, after § 1b.
   The first version proposed a per-key half-life of 1, 2, 4, then 8 days by practice days. That
   put forgetting on a scale of days and had no support beyond one reading of Danna.)*
2. **Accuracy bar:** keep 0.90 and 0.95, and test them against the **lower confidence bound**
   instead of the raw proportion, for Known and for the anchor rung. Keep the 90-press floor as
   the dose.
3. **Speed term:** add it to Known, as a ratio of 2.0 against the child's own median on the two
   bump keys together, over equal-sized recent samples, skipped when either side is thin, and
   with no term for the bump keys themselves. *(Two per-finger baselines were considered the same
   day and dropped: § 3 gives the reasons. The finger differences found are tens of milliseconds
   and the ratio's tolerance is hundreds.)* Record how often a
   prompt had to be repeated before it was answered, and count such an answer as slow. Give a key
   that fails only on speed a need, so it cannot hold a slot unpractised.

   *Decided: as proposed, at ratio 2.0, with one change to the baseline. The developer asked for
   recent presses on well-practised keys to join `f` and `j` once there are any, because the two
   bump keys come up rarely outside the ramp-up and their samples would go stale. How the pool is
   defined is in ADR-027.*
4. **Early press:** store a signed latency from the letter's expected end, with the letter's
   expected length beside it, a floor at half the letter's usual length, and NULL for a re-spoken
   letter and for the resume announcement. The speed term's ratio is taken from the enqueue.

   *Decided: differently in two ways. The floor is a physical floor of 250 ms from the enqueue, a
   press before it is not an attempt at all, and every later press counts and is timed (§ 4, "The
   half-letter floor was withdrawn"). And the columns are the other way round: `latency_ms` is the
   plain time from the enqueue, which is what the speed term reads and needs no letter length, and
   the signed number is its own column, `after_letter_ms`. The first form, built as proposed here,
   could not time an answer until some letter had run to its end in the session; the review found
   that a child who answers every letter early would then never be timed. ADR-011 has the result.*

Every number in this proposal is a starting point for #12h to hear and the pilot to calibrate.
None comes from the literature.

---

## Sources

**Read in full**

- Settles, B. & Meeder, B. (2016). *A Trainable Spaced Repetition Model for Language Learning.* ACL 2016. <https://aclanthology.org/P16-1174/>
- Tatel, C. E. & Ackerman, P. L. (2025). *Procedural Skill Retention and Decay: A Meta-Analytic Review.* Psychological Bulletin. doi:10.1037/bul0000481. Accepted manuscript read, not the copy of record.
- Arthur, W., Bennett, W., Stanush, P. L. & McNelly, T. L. (1998). *Factors That Influence Skill Decay and Retention: A Quantitative Review and Analysis.* Human Performance 11(1), 57–101. Tables 3 and 4 read from the page scans.
- Baddeley, A. D. & Longman, D. J. A. (1978). *The Influence of Length and Frequency of Training Session on the Rate of Learning to Type.* Ergonomics 21(8), 627–635. Scan; the retention figure's values could not be read off, only the text.
- Dhakal, V., Feit, A. M., Kristensson, P. O. & Oulasvirta, A. (2018). *Observations on Typing from 136 Million Keystrokes.* CHI 2018. <https://userinterfaces.aalto.fi/136Mkeystrokes/>
- Fuller, J. L. & Fienup, D. M. (2018). *A Preliminary Analysis of Mastery Criterion Level: Effects on Response Maintenance.* Behavior Analysis in Practice 11(1), 1–8. <https://pmc.ncbi.nlm.nih.gov/articles/PMC5843573/>
- McDougale, C. B., Richling, S. M., Longino, E. B. & O'Rourke, S. A. (2019). *Mastery Criteria and Maintenance: a Descriptive Analysis of Applied Research Procedures.* Behavior Analysis in Practice 13(2), 402–410. <https://pmc.ncbi.nlm.nih.gov/articles/PMC7314871>
- Whelan, R. (2008). *Effective Analysis of Reaction Time Data.* The Psychological Record 58, 475–482.
- Marslen-Wilson, W. D. (1987). *Functional Parallelism in Spoken Word-Recognition.* Cognition 25, 71–102. The section on early selection; Grosjean (1980) is quoted from it.
- Karni, A., Meyer, G., Rey-Hipolito, C., Jezzard, P., Adams, M. M., Turner, R. & Ungerleider, L. G. (1998). *The Acquisition of Skilled Motor Performance: Fast and Slow Experience-Driven Changes in Primary Motor Cortex.* PNAS 95(3), 861–868. <https://pmc.ncbi.nlm.nih.gov/articles/PMC33809/>
- van den Bergh, M., Schmittmann, V. D., Hofman, A. D. & van der Maas, H. L. J. (2015). *Tracing the Development of Typewriting Skills in an Adaptive E-Learning Environment.* Perceptual and Motor Skills 121(3), 727–745. <https://pure.uva.nl/ws/files/29156171/23.25.PMS.pdf>
- Dorfberger, S., Adi-Japha, E. & Karni, A. (2007). *Reduced Susceptibility to Interference in the Consolidation of Motor Memory before Adolescence.* PLoS ONE 2(2), e240. <https://pmc.ncbi.nlm.nih.gov/articles/PMC1800346/>
- Julius, M. S. & Adi-Japha, E. (2015). *Learning of a Simple Grapho-Motor Task by Young Children and Adults: Similar Acquisition but Age-Dependent Retention.* Frontiers in Psychology 6, 225. <https://pmc.ncbi.nlm.nih.gov/articles/PMC4350392/>
- Adi-Japha, E., Berke, R., Shaya, N. & Julius, M. S. (2019). *Different Post-Training Processes in Children's and Adults' Motor Skill Learning.* PLoS ONE. <https://pmc.ncbi.nlm.nih.gov/articles/PMC6328138/>
- Van Roy, A. et al. (2026). *Neural Correlates of Motor Sequence Learning and Enhanced Offline Consolidation in 7–11-Year-Old Children.* Human Brain Mapping. <https://pmc.ncbi.nlm.nih.gov/articles/PMC13345992/>. Their 2024 behavioural paper (Communications Psychology) was not read.
- Glickman, M. E. *The Glicko System.* <https://www.glicko.net/glicko/glicko.pdf>. The author's description; Glickman (1999), Applied Statistics 48(3), was not read.
- US Office of Personnel Management, *General Schedule Qualification Standards*, Clerical and Administrative Support Positions, proficiency requirements. <https://www.opm.gov/policy-data-oversight/classification-qualifications/general-schedule-qualification-standards/>
- American Printing House for the Blind, *Talking Typer for Windows: User's Manual* (2016). <https://aphtech.org/tt_doc.htm>
- Wisconsin Department of Public Instruction, *Keyboarding at the Elementary Level.* <https://dpi.wi.gov/bit/standards/elementary-keyboarding>
- keybr.com source, `packages/keybr-lesson/lib/guided.ts`. <https://github.com/aradzie/keybr.com>. The unlock rule was read; the default target speed (35 WPM) is from secondary descriptions.

**Abstract or author's summary only**

- Cepeda, N. J., Vul, E., Rohrer, D., Wixted, J. T. & Pashler, H. (2008). *Spacing Effects in Learning: A Temporal Ridgeline of Optimal Retention.* Psychological Science 19(11), 1095–1102.
- Aoki, T., Francis, P. R. & Kinoshita, H. (2003). *Differences in the Abilities of Individual Fingers during the Performance of Fast, Repetitive Tapping Movements.* Experimental Brain Research 152, 270–280.
- Lachnit, H. & Pieper, W. (1990). *Speed and Accuracy Effects of Fingers and Dexterity in 5-Choice Reaction Tasks.* Ergonomics.
- Ekşioğlu, M. & İşeri, A. (2015). *An Estimation of Finger-Tapping Rates and Load Capacities and the Effects of Various Factors.* Human Factors. The per-finger rates quoted are from a summary of its table.
- Pan, S. C. & Rickard, T. C. (2015). *Sleep and Motor Learning: Is There Room for Consolidation?* Psychological Bulletin 141(4), 812–834.
- Savion-Lemieux, T. & Penhune, V. B. (2005). *The Effects of Practice and Delay on Motor Skill Learning and Retention.* Experimental Brain Research 161, 423–431.
- Richling, S. M., Williams, W. L. & Carr, J. E. (2019). *The Effects of Different Mastery Criteria on the Skill Maintenance of Children with Developmental Disabilities.* Journal of Applied Behavior Analysis 52, 701–717. Two summaries of its conditions disagree (60/80/100% and 80/90/100%); both report the 100% result.
- Wong, K. K., Fienup, D. M., Richling, S. M., Keen, A. & Mackay, K. (2022). *Systematic Review of Acquisition Mastery Criteria and Statistical Analysis of Associations with Response Maintenance and Generalization.* Behavioral Interventions 37(4), 993–1012.
- Snyder, K. M., Ashitaka, Y., Shimada, H., Ulrich, J. E. & Logan, G. D. (2014). *What Skilled Typists Don't Know About the QWERTY Keyboard.* Attention, Perception, & Psychophysics 76(1), 162–171.
- Doughty, S. S., Chase, P. N. & O'Shields, E. M. (2004). *Effects of Rate Building on Fluent Performance: A Review and Commentary.* The Behavior Analyst 27, 7–23.
- Danna et al., both graphomotor papers: see [references.md](references.md).

**Search summaries only**

- Dietrich, S., Hertrich, I. & Ackermann, H. (2013), on blind listeners' comprehension of ultra-fast speech. The syllable rates quoted in § 4 are from a summary of it; the paper was not opened.
- A study of simple auditory reaction time in congenitally blind adults (0.21 s against 0.32 s). Not identified beyond the summary, so it is not a citation and should be found before it is relied on.

**Wanted and not obtained**

- Hill, L. B., Rejall, A. E. & Thorndike, E. L. (1913), *Practice in the Case of Typewriting*; Hill, L. B. (1934), *A Quarter Century of Delayed Recall*; Hill, L. B. (1957), *A Second Quarter Century of Delayed Recall, or Relearning at Eighty.* Paywalled.
- US Army Research Institute (1979), *Typewriting: Retention and Relearning*, DTIC ADA072369. Download refused.
- Salthouse, T. A. (1986). *Perceptual, Cognitive, and Motoric Aspects of Transcription Typing.* Psychological Bulletin 99(3), 303–319.
- Häger-Ross, C. & Schieber, M. H. (2000). *Quantifying the Independence of Human Finger Movements: Comparisons of Digits, Hands, and Movement Frequencies.* Journal of Neuroscience 20, 8542–8550. Known only as cited.
- Cepeda et al. (2006), Psychological Bulletin; Luce (1986), *Response Times*; Miller (1988), *A Warning About Median Reaction Time* (the last two are known through Whelan).
- Any primary for UK or Australian civil-service typing tests, for accuracy percentages in a state keyboarding standard, or for children's reaction times to spoken letters.
