# Research note: the ramp-up phases — what practice-schedule research supports

> **Status:** Findings, a first proposal, and the direction the developer chose on 2026-10-10 after [ADR-033](../adr/0033-rest-keys-and-keyboard-alignment.md), which differs from the proposal: see [§ What was decided](#what-was-decided). **ADR-024 was amended on 2026-10-10** ([§ The ramp-up restated](../adr/0024-drill-content-and-lesson-granularity.md#the-ramp-up-restated-four-objectives-and-a-ladder-of-three-levels), alpha-plan #12m), which settles the list at the end of that section; the ADR is now the design and this note is its evidence. It is not yet built.
> **Date:** 2026-10-10 (follows the whole-repo review of 2026-10-06, alpha-plan #12k, findings E1 to E3)
> **Feeds:** [ADR-024](../adr/0024-drill-content-and-lesson-granularity.md) § New-key ramp-up and § Ramp-up variability
> **See also:** [ADR-033](../adr/0033-rest-keys-and-keyboard-alignment.md) (2026-10-10) removes Stage 0, so the `r u` and `v m` rows of § What the generator does today describe steps that go. Its ADR-024 amendment and this note's proposal are best decided together ([alpha-plan](../alpha-plan.md) #12m).
> **Sources:** listed at the end with how each was read; PDFs are in the gitignored `docs/research/references/`

**One-line summary:** Research on practice order supports starting a new key with a short
predictable stretch and then mixing it, which is the shape ADR-024 already has. It does not support
unpredictability as a motor-learning benefit for children: the effect of random over blocked
practice in under-18s is close to zero. The reason to draw prompts at random is a different one.
A child who can predict the next letter does not need to listen to it, and listening is the skill.
Measured on the current generator, the new letter is fully predictable through Phase A and, for
every step that reaches off the home row, through Phase B as well. The first proposal was to keep Phase A
as it is, draw Phase B prompt by prompt with repeats allowed up to two in a row, and shrink Phase C.
After ADR-033 the developer chose a cleaner shape: the location is introduced once, then three
levels each add one difficulty (Reach, Choose, Combine), and one bar decides when a new letter may
come. ADR-024 names the third level Travel.

---

## How to read this note

Every claim is tagged with how its source was read:

- **[full]** the paper itself was read, and figures are quoted from it.
- **[abstract]** only the abstract was read.
- **[cited]** known only through another paper that cites it. Not verified.
- **[own]** this note's own measurement or reasoning, not a finding from the literature.

No study was found of blind children, or of any children, learning to type under different practice
orders. Every source is applied by analogy. Most are studies of sighted adults learning throwing,
putting or timing tasks.

Three terms from that literature are used throughout. **Blocked** practice finishes all trials of
one task before starting the next (`f f f f j j j j`). **Serial** practice rotates through the tasks
in a fixed order (`f j f j f j`). **Random** practice draws the next task unpredictably. The
finding that random practice is worse during practice and better on a later test is called the
contextual interference effect.

## The question

ADR-024 takes a new key through Phase A (the key alone, ten correct in a row), Phase B (alternating
with its home-row anchor, twenty correct with at most one rejection), Phase C (corpus bigrams with
known keys, thirty presses at 85%) and then the steady-state mix. Its § Ramp-up variability
(#12d) added five properties, the first being that the previous prompt does not determine the next.

The review of 2026-10-06 found that the first property does not hold in practice (E1, E2) and that
the first step's Phase C drills each letter against itself (E3). That raised the wider question
this note addresses: what does research say about the phases themselves?

1. Should a new key start with predictable practice at all?
2. Does unpredictability help, and if so why?
3. May a prompt follow itself?
4. Should a letter the child missed be asked again?
5. Is there evidence for a bigram phase between single letters and the full mix?

## What the generator does today **[own]**

Measured by running the real drill generator over the first seven English steps with a child who
answers every prompt correctly, five seeds. "Told by the previous prompt" is the share of the new
key's prompts that came after a prompt which is followed by that key at least nine times in ten.

| Step | Phase | Prompts | New key told by the previous prompt | New key follows itself |
|---|---|---|---|---|
| `f j` | A | 20 | 100% | 0% |
| `f j` | B | 40 | 100% | 0% |
| `f j` | C | 80 | 0% | 62% |
| `r u` | A | 40 | 97% | 0% |
| `r u` | B | 80 | 100% | 0% |
| `r u` | C | 143 | 21% | 18% |
| `v m` | A | 40 | 98% | 0% |
| `v m` | B | 80 | 100% | 0% |
| `v m` | C | 152 | 0% | 13% |
| `d k` | A | 20 | 100% | 0% |
| `d k` | B | 80 | 0% | 0% |
| `d k` | C | 149 | 0% | 4% |
| `s l` | A | 20 | 100% | 0% |
| `s l` | B | 80 | 0% | 0% |
| `s l` | C | 111 | 0% | 35% |
| `a` | A | 20 | 100% | 0% |
| `a` | B | 60 | 0% | 0% |
| `a` | C | 71 | 0% | 12% |
| `g h` | A | 20 | 100% | 0% |
| `g h` | B | 80 | 0% | 0% |
| `g h` | C | 150 | 0% | 2% |

Three things follow from the table.

- **Phase A is a fixed cycle everywhere.** In the literature's terms it is serial practice, not
  blocked: the prompts alternate, they are never the same key ten times running.
- **Phase B is unpredictable only for home-row steps.** For a step that reaches off the home row
  (`r u`, `v m`) and for the first step (`f j`), the #12d shuffle varies which unit comes next, and
  the new key is still always announced by the prompt before it.
- **Phase C is the largest phase and the least examined.** A pair step is about 250 prompts, of
  which about 150 are Phase C. In the first step it is 80 prompts of `ff` and `jj`.

## 1. Starting predictable, then mixing

### What the sources say

**In adults, a schedule that starts blocked and ends random beats both pure schedules.** Porter and
Magill **[full]**, read as Porter's dissertation, which contains both experiments. In Experiment 1,
60 adult novices practised golf putts from three distances for 81 trials. The increasing group did
27 blocked trials (nine per distance), then 27 serial, then 27 random. On a retention test 24 hours
later their error was 2.14 against 2.71 for the random group and 2.72 for the blocked group, both
differences significant. On a transfer test they beat the random group only. In Experiment 2, 96
novices practised three basketball passes. The increasing group beat both other groups on retention
and on transfer, and random beat blocked.

**In children the same schedule has been tested once, and the result is weak.** Saemi et al.
**[full]**: 36 boys, mean age 10.5, threw a tennis ball at a target from three distances for 81
trials in one session, with the same 27/27/27 split. On a retention test the next day the increasing
group scored 70.97, the random group 63.19 and the blocked group 59.02. Only the difference between
increasing and blocked was significant. The authors call the support "albeit weak". There was no
transfer test.

**Across children's studies, random practice has little or no advantage over blocked.** Czyż et al.
pooled the literature twice **[full]**. For transfer tests, the under-18 effect of random over
blocked practice was 0.12 standard deviations (95% interval −0.28 to 0.53), against 0.54 for adults.
For retention tests it was 0.02 (−0.90 to 0.94), against 0.63 for adults. Brady's earlier
meta-analysis gave 0.10 for young participants and 0.35 for adults **[cited]**. Two cautions come
with these figures. The effect is much larger in laboratory studies than in applied ones (0.75
against 0.34 for transfer, 0.92 against 0.23 for retention), and almost all the studies of young
people are applied ones: 400 of the 418 young participants in the retention analysis. Age and
setting cannot be separated in this data.

**The quality of the children's studies is low.** Graser et al. reviewed contextual interference in
children **[full]**. Of 25 studies, 22 scored zero of seven on their quality scale. The one area
with moderate evidence for random practice was handwriting, on transfer tests only. They also report
Jarus and Goverover, where of three age groups only the seven-year-olds differed by schedule, and
those did better with blocked practice **[cited]**. ADR-024 already cites that study.

**The nearest child task favours random practice.** Ste-Marie et al. **[abstract]**: in three
experiments, elementary school children (44, 50 and 78 of them) wrote three letters 24 times each,
either one letter at a time or intermixed. Intermixed practice gave better retention and transfer.
This is the handwriting result Graser's review rates as moderate evidence. Writing a named letter on
cue is closer to pressing a named key than throwing is.

**A gentle start is supported for children who find the task hard.** Capio et al. **[abstract]**:
216 children aged 8 to 12 practised throwing with the task made harder in small steps, so that
errors stayed rare, or made easier in small steps. Children of low ability gained from the
error-reduced order, and the gain held when they did a second task at the same time. The review by
the same group **[full]** argues the general case but reports no new data.

**Learners misjudge which schedule is working.** Abushanab and Bishara **[full]**: 25 people with
1 to 17 years of piano training practised key sequences in fixed or random order. Fixed order was
faster during practice. Random order was faster two days later. The participants judged that fixed
order had taught them more. Lee and Simon's chapter **[full]** adds the other side: random practice
feels like slower progress, which may discourage a learner from continuing.

### What the sources do not say

- Nothing tests an increasing schedule on a discrete key-press task, on children younger than ten,
  or on blind learners.
- Nothing gives a dose. Porter's 27 blocked trials, nine per task, were chosen as a third of 81,
  not found to be best.
- Bangert and Altenmüller **[full]** is sometimes quoted as showing that a key-to-sound map forms in
  20 minutes. What they measured after 20 minutes was a change in EEG activity in adults. Wrong-key
  errors fell from 0.72 to 0.54 per note over ten sessions, and a group whose key-to-sound map was
  reshuffled every session did not improve.

### What follows for the design **[own]**

The shape ADR-024 has, a predictable start that becomes mixed, is the best-supported one available.
The adult evidence for it is clear and the one children's study points the same way. No source
argues for starting a new key in the full random mix.

The evidence gives no reason to shorten or lengthen Phase A. Its ten correct per key is about the
size of the blocked stretch in the two schedule studies. What it does suggest is that the
predictable stretch should be one phase and not two. Today a reach step is predictable for Phase A
and Phase B together, 120 prompts, before anything is drawn.

## 2. Why unpredictability, if not for motor learning

### What the sources say

**A fixed rotating order did about as well as a random one.** Lee and Magill **[full]**: adults
learned three movement patterns over 54 trials in blocked, serial or random order. In Experiment 2
the serial and random groups did not differ at retention, and both were faster than the blocked
group. In Experiment 3, a timing task, the serial group fell between the other two and differed
from neither. Their explanation is that what matters is doing a different task from the one just
done, because the learner then has to rebuild the plan for the movement. Whether the next task
could be predicted made little difference. Simon, Lee and Cullen's count of switches (§ 4) points
the same way.

**With predictable material, people stop using the stimulus.** This is the existing grounding in
ADR-024 § Research grounding, from serial-reaction-time studies **[cited there, not re-read for
this note]**: with a deterministic sequence, learners move from responding to each stimulus to
executing a plan, and anticipation shows up before the stimulus appears.

**Knowledge of key positions is in the hands.** Snyder et al. **[full]**: skilled typists, with
about twelve years of practice, could place only 57% of letters on a blank keyboard from memory.
Recall cued by a letter was 78.8% with hands free and 66.8% when the hands were kept busy. People
who had used a Dvorak layout for about two hours knew as much about it explicitly as the skilled
typists knew about QWERTY.

### What follows for the design **[own]**

The two findings answer different questions. Lee and Magill is about learning the movement, and for
the movement a fixed alternation is as good as a random order. Phase A's cycle is therefore not a
weakness as motor practice.

The serial-reaction-time finding is about the link from the prompt to the movement. Takki's prompt
is a spoken letter, and what the child must learn is to press the key for the letter they hear. In
a fixed cycle the child can press correctly without hearing anything. Those presses are then counted
as evidence that the child knows the key. This is the case for unpredictability, and ADR-024
already makes it. It is an argument about what the child is practising and what the records mean,
and it holds whatever the size of the contextual interference effect in children.

So property 1 is right and its implementation falls short of it. The table shows the gap: for reach
steps the new letter is never the one the child has to listen for until Phase C.

## 3. A prompt following itself

*Settled in discussion: repeats are allowed. Property 5 ("no prompt follows itself") is to go.*

### What the sources say

**Every random schedule read here allows an immediate repeat and caps the run at two.** Lee and
Magill **[full]** constrained their random order so that no pattern "occurred more than twice in
succession". Porter and Magill **[full]** and Saemi et al. **[full]** use the same cap.
Abushanab and Bishara's random sequences **[full]** include immediate repeats. Simon, Lee and
Cullen **[full]** describe random practice as "usually with the restriction of no more than two
repetitions of a task".

**A repeat is easier than a change.** Lee and Magill argue that on an immediate repeat the learner
can reuse the plan still in mind instead of rebuilding it, which is why blocked practice looks good
and teaches less. Notebaert and Soetens **[full]** report the same idea from reaction-time work at
second hand: a repeated stimulus and response is fast because it bypasses the step of choosing the
response, citing Rabbitt and Pashler and Baylis **[cited]**.

### What follows for the design **[own]**

Property 5 is what forces a fixed cycle. With two single prompts in a hand's inventory, "never the
same twice" leaves only strict alternation (finding E1). Dropping it removes the cause.

A repeat is not harmful, and it is weaker evidence than a press after a change. With four equally
likely prompts a repeat comes up one time in four and a run of three about one time in sixteen. A
cap of two in a row, the convention above, keeps the natural rate of repeats and removes the long
runs. The cap should be configurable.

Property 2, the anchor invariant, needs rewording and nothing more. A repeated reach prompt asks the
same finger for the same key, so the hand is not asked for a second, different reach while off
home. "Between two *different* reach prompts of the same hand there is an anchor prompt of that
hand" still holds for a draw that respects it.

## 4. Staying on a letter after a miss

*Settled in discussion: this is wanted. How is open.*

### What the sources say

**One study tests it directly.** Simon, Lee and Cullen **[full]**: 48 undergraduates, mean age
20.7, learned three five-key sequences on a number pad, each to be completed in its own target time.
Two groups stayed on a sequence until they succeeded and then switched to another at random.
Success was a time within 5% of the target, on one trial for the first group and on two consecutive
trials for the second. A blocked and a random group did the same number of trials as the first
group. Practice ended after 24 correct-sequence trials of each pattern, and no pattern ran for more
than 24 trials in a row.

| Group | Error in practice | Error next day | Switches of task |
|---|---|---|---|
| Blocked | 3.47% | 13.56% | 2 |
| Stay until one success | 4.76% | 8.71% | 34 |
| Stay until two in a row | 5.73% | 11.75% | 14 |
| Random | 5.99% | 7.46% | 71 |

Only two differences were significant in the main analysis: blocked beat random in practice, and
random beat blocked the next day. The one-success group did not differ from any group in practice.
The next day its advantage over blocked fell just short (p = .064) and was significant in a
follow-up comparison of those two groups alone. The two-in-a-row group did more trials than the
others and did not differ from any group the next day. Across all learners, more switches in
practice went with less error the next day (r = −.47).

The authors call the effects "moderate". The one-success schedule did not beat random practice at
anything, and they say that if this is replicated there is little need for tailored schedules.

**A wrong key was treated differently from a miss.** In that study a trial with the wrong keys was
not counted and was done again. "Losing" meant the right keys at the wrong speed.

**The idea behind such schedules is that difficulty should match the learner.** Guadagnoli and Lee
**[abstract]** propose that learning is greatest at a level of difficulty that depends on the
learner's skill, so a schedule that suits a practised learner can be too hard for a beginner.

**An older design puts the missed trial back later.** Lee and Magill **[full]** repeated an errored
trial at the end of its set for the random groups, not immediately.

### What follows for the design **[own]**

Takki already stays on a letter in one sense. A wrong key is rejected and the prompt stays open
until the right key is pressed ([ADR-012](../adr/0012-audio-feedback-design.md)). That second press
is a correction, made knowing which key was wrong. It is not a fresh answer to the prompt.

What the study supports is the lighter rule: after a missed prompt, ask the same letter again, and
move on as soon as one prompt is answered correctly first time. Requiring two in a row looked like
blocked practice, despite more trials.

The support is modest and should be stated as such. Staying until one success cost nothing against
random practice that the study could detect, and it kept most of the benefit over blocked practice.
It was not better than random practice at learning. The case for it in Takki is therefore the one
the authors give for trying it, that moving a learner off a task they have not yet got right is
poor for motivation, together with the developer's judgment. It is not a learning gain.

The rule would also fire far less often in Takki. Those learners succeeded on roughly two trials in
five, so staying halved the number of switches. A child at 90% first-press accuracy would be held
on about one prompt in ten. For that child the schedule stays close to a random draw, which is the
end of the table that did best the next day.

A miss followed by its repeats can exceed the cap of two from § 3. The study capped a stay at 24
trials. Takki needs its own, much lower cap, so that a child who keeps missing one key is moved on
and meets it again later. Both numbers should be configurable.

## 5. A bigram phase

### What the sources say

**Practising words teaches something that practising their letters does not.** Crump and Logan
**[full]**: 32 skilled adult typists typed 20 words, 24 times each, on an unfamiliar projected
keyboard where their speed fell from 70 to 33 words per minute. Afterwards the interval between
keys was 235 ms in the practised words, 253 ms in new words made of the same letters and 267 ms in
new words made of other letters. Looking at letter pairs, practised letters were 18 ms faster than
unpractised ones, practised pairs a further 16 ms, and pairs inside practised words a further
18 ms. Letters, pairs and words each carried their own gain.

**Typists are faster on frequent letter pairs, at every level of skill measured.** Pinet et al.
**[full, the passages on letter-pair frequency]**: among university students, frequent pairs were
typed faster by both the more and the less proficient group. Behmer and Crump found among 400
typists that sensitivity to pair frequency rose with speed **[cited]**. Pinet et al. found the
opposite direction and attribute it to even their weaker typists being well practised.

### What the sources do not say

- All of this is about adults who can already type. No study was found of novices or children
  learning letter pairs.
- Nothing compares a dedicated bigram phase with going straight from single letters to mixed
  practice. Phase C's existence is not contradicted and its size is not supported.
- Nothing supports drilling a letter against itself.

### What follows for the design **[own]**

Practice in sequences is worth having, and the steady state already is practice in sequences. Since
#12e it also keeps a large share of the next blocks for a key that has just left its ramp-up. Phase C
and the first blocks of the steady state therefore do much the same job, and Phase C is where 60%
of a step's prompts go.

For the first step there are no known keys to pair with, so Phase C is `ff` and `jj` (finding E3).
A step with no partners should have no Phase C.

## One more constraint: the hand drifts **[own, from one source]**

Brown, Rosenbaum and Sainburg **[full]**: five sighted adults made repeated back-and-forth arm
movements with the hand on an air sled and no touch landmark. When sight of the hand was removed,
the hand's position drifted by about 4 cm within the first few movements and 7.9 cm by the fortieth,
while the distance and direction of each movement stayed accurate. The authors note that touch is a
strong signal against this kind of drift.

For a blind child this is the argument for the anchor in plain terms. The reach itself stays
accurate, and where it starts from does not, unless the hand comes back to a key it can feel. It
supports keeping reach-and-return in Phase A and keeping the reworded anchor invariant in Phase B.

## Proposal, as first written

*Written before ADR-033. Kept for the reasoning; the next section says what was decided instead.*

1. **Phase A, "find it": keep.** A predictable reach-and-return cycle, the same size as now. Stated
   in the ADR as the one deliberately predictable phase, and why.
2. **Phase B, "pick it out": draw each prompt** from the phase's closed inventory, instead of
   shuffling units. A prompt may follow itself, at most twice in a row. A hand that is off home is
   not asked for a different reach. This removes property 5, fixes E1 and E2, and makes property 1
   true for reach steps.
3. **After a missed prompt, ask the same letter again**, and return to the draw after one
   first-press-correct answer, or after a small number of tries. In Phase B to begin with. Chosen
   for the child's sake; the evidence says it does no harm, not that it teaches more.
4. **Phase C, "use it": make it smaller, and skip it for a step with no partners.** How much
   smaller is a judgment, not a finding.
5. **Keep every number configurable**: the cap on runs, the repeat after a miss, Phase C's length.

## What was decided

Decided by the developer in discussion on 2026-10-10, after ADR-033 was accepted. Each item is
marked **[D]** where the developer stated or accepted it, and **[P]** where it is this note's
proposal that the developer has not yet answered. This is the input to the ADR-024 amendment.

*(2026-10-10, after the amendment was written: every **[P]** and every item under "Still to settle" below is answered in [ADR-024 § The ramp-up restated](../adr/0024-drill-content-and-lesson-granularity.md#the-ramp-up-restated-four-objectives-and-a-ladder-of-three-levels). Three things differ from this section. The level called "Combine" here is named **Travel** there, and it has no words: whole words are Layer 2. At Reach the cycle is the letter and then the rest cue, not the cue first. A predictable press counts toward nothing except whether the child reaches the key, which also answers the question about Known.)*

**Why the proposal above was set aside.** ADR-033 moved three of the ramp-up's jobs to the rest
tier: the place a finger returns to is its rest key, the anchor bar that the "anchor between
reaches" rule fed is retired, and a rest letter has no location to find. The questions the proposal
then raised (what a rest letter alternates with, what stands in for a rest key with no letter,
whether the anchor rule stays) were about keeping Phase B's machinery after its purpose had moved.
The developer's reading: the intent of the phases was always a gradual increase in difficulty, as
in traditional typing instruction, and it had become blurred. **[D]**

**Four objectives, each with one owner. [D]**

| Objective | What serves it | Differs by kind of letter? | Measure |
|---|---|---|---|
| 1. Introduce the location of the new letter | The script, described from the finger's rest key, then guided presses | Yes, and only here | None; it is guidance |
| 2. Give gradually increasing difficulty using that location | A short ladder of practice levels | No | A light rule to move on **[P]** |
| 3. Decide when the letter is stable enough for a new letter to be added | One bar | No | Read only where the child had to listen |
| 4. Decide when the letter is Known, after which its practice follows the general rules | ADR-027 as it stands | No | Known |

Objectives 3 and 4 are the two halves of the existing introduction gate: this step's ramp-up has
ended, and a slot is free.

**The ladder: each level adds one difficulty. [D]**

| Level | What is new | What stays easy |
|---|---|---|
| Reach | The finger leaves its rest key, finds the letter and comes back | Only this letter; the child knows what is coming |
| Choose | The child must listen: the letter is drawn among a few active ones | Single letters, a small set |
| Combine | The finger arrives from another key: pairs, and words where they exist | A few partners only |
| General practice | The full active set, planned by need | |

**The return is forced by asking for the rest key. [D]** At the Reach level Takki tells the child
to press that finger's rest key, then asks for the letter. It is the same for every finger and
every language, and it works whether or not the rest key carries a letter. Repeating one letter
with nothing between teaches little, because the finger can stay on the key (§ 3).

**What follows for a rest letter. [D]** It has no reach, so it has no Reach level and starts at
Choose. The same holds for the two bump letters. ADR-033 says a rest letter's ramp-up is "the
ordinary one"; the amendment has to restate that as the ordinary ladder without its first level.

**A press the child could predict does not count toward objective 3. [D]** The bar is read on
Choose and Combine presses only. Whether such presses count toward Known is not yet answered.

**Carried over from the first proposal.** A prompt may follow itself **[D]**, at most twice in a
row **[P]**. A missed letter is asked again **[D]**; for how long is open **[P]**. Every number is
configurable.

**What goes.** The special cases for the first step, Stage 0's own content and the borrowed anchor
of a solo step belong to objective 1, not to the levels. The anchor rule and the fixed direction of
a reach unit, which made the blocks a fixed cycle (E1, E2), are not carried into the ladder. The
three bars of Phases A, B and C become one.

**Still to settle in the ADR-024 session.**

- The rule for moving up a level, and its numbers.
- The one bar for objective 3. Phase C's (30 presses at 85%, and not too slow) is the candidate.
- Whether predictable presses count toward Known.
- What Takki does when the press after the rest cue is not the rest key. In the alignment there is
  no wrong answer; here the finger has a chosen key.
- Whether the rest cue is spoken or a sound, and that ADR-033 has to allow a rest key to be asked
  for during practice. It says a rest key is never prompted by character, which a cue by finger
  respects, and that alignment presses are untimed and kept apart from `key_attempts`.
- Which letters make up the small set at Choose, and how partners are limited at Combine.
- What Combine uses for content in Alpha, where real words (Layer 2) are not built.
- How the levels are recorded: ADR-011's `ramp_up_phases` holds the three phases as events today.

## What this leaves open

- **Two children's studies in full.** Ste-Marie et al. and Capio et al. (2013) would firm up § 1.
  Both are paywalled.
- **How many tries a stay may last.** The one study capped it at 24, for adults who missed more
  often than they succeeded. Nothing gives a number for a child.
- **Whether the steps of the curriculum after Stage 0 keep Phase C's accuracy bar**, or pass to the
  steady state on Phase B's bar alone.
- **Whether a hand returns home on its own after a reach.** The draw in item 2 assumes the anchor
  prompt is what brings it back. A child who returns unprompted makes the constraint harmless, and
  nothing here measures which children do.
- **How much the hands should alternate** (ADR-024 open question 1, roadmap § D). A draw over both
  hands' inventories alternates about half the time without a rule. Whether that is the right
  amount is the same open question as before.
- **Phase B's exit bar under a draw.** Twenty correct with one rejection was set for a fixed cycle.
  The same twenty are harder when the child has to listen, which ADR-024 already notes for Phase A.
- **None of this has been heard.** The ear check owed since #12d applies to whatever is built.

## Sources

PDFs of the items marked *(local)* are in `docs/research/references/`.

**Read in full**

- Lee, T. D. & Magill, R. A. (1983). *The Locus of Contextual Interference in Motor-Skill Acquisition.* Journal of Experimental Psychology: Learning, Memory, and Cognition 9(4), 730–746. *(local)*
- Porter, J. M. (2008). *Systematically Increasing Contextual Interference Is Beneficial for Learning Novel Motor Skills.* Doctoral dissertation, Louisiana State University. <https://repository.lsu.edu/gradschool_dissertations/2980> *(local, 284 pp.)* Published as Porter, J. M. & Magill, R. A. (2010), Journal of Sports Sciences 28(12), 1277–1285; the journal version was not read.
- Saemi, E., Porter, J. M., Ghotbi Varzaneh, A., Zarghami, M. & Shafinia, P. (2012). *Practicing Along the Contextual Interference Continuum: A Comparison of Three Practice Schedules in an Elementary Physical Education Setting.* Kinesiology 44(2), 191–198. <https://hrcak.srce.hr/94557> *(local)*
- Czyż, S. H., Wójcik, A. M. & Solarská, P. (2024). *The Effect of Contextual Interference on Transfer in Motor Learning: A Systematic Review and Meta-Analysis.* Frontiers in Psychology 15, 1377122. <https://pmc.ncbi.nlm.nih.gov/articles/PMC11349744/>
- Czyż, S. H., Wójcik, A. M., Solarská, P. & Kiper, P. (2024). *High Contextual Interference Improves Retention in Motor Learning: Systematic Review and Meta-Analysis.* Scientific Reports 14, 15974. <https://pmc.ncbi.nlm.nih.gov/articles/PMC11237090/> The results and discussion of the age and setting analyses were read.
- Graser, J. V., Bastiaenen, C. H. G. & van Hedel, H. J. A. (2019). *The Role of the Practice Order: A Systematic Review About Contextual Interference in Children.* PLoS ONE 14(1), e0209979. <https://pmc.ncbi.nlm.nih.gov/articles/PMC6342307/>
- Simon, D. A., Lee, T. D. & Cullen, J. D. (2008). *Win-Shift, Lose-Stay: Contingent Switching and Contextual Interference in Motor Learning.* Perceptual and Motor Skills 107(2), 407–418. doi:10.2466/pms.107.2.407-418 *(local)*
- Abushanab, B. & Bishara, A. J. (2013). *Memory and Metacognition for Piano Melodies: Illusory Advantages of Fixed- over Random-Order Practice.* Memory & Cognition 41(6), 928–937. *(local)*
- Lee, T. D. & Simon, D. A. (2004). *Contextual Interference.* In A. M. Williams & N. J. Hodges (eds), *Skill Acquisition in Sport*, 29–44. Routledge. The sections on hybrid schedules and on learners' judgments were read.
- Snyder, K. M., Ashitaka, Y., Shimada, H., Ulrich, J. E. & Logan, G. D. (2014). *What Skilled Typists Don't Know About the QWERTY Keyboard.* Attention, Perception, & Psychophysics 76(1), 162–171. *(local)* Listed as abstract-only in [known-decay-accuracy-speed.md](known-decay-accuracy-speed.md); now read in full.
- Notebaert, W. & Soetens, E. (2003). *The Influence of Irrelevant Stimulus Changes on Stimulus and Response Repetition Effects.* Acta Psychologica 112, 143–156. *(local)*
- Crump, M. J. C. & Logan, G. D. (2010). *Episodic Contributions to Sequential Control: Learning From a Typist's Touch.* Journal of Experimental Psychology: Human Perception and Performance 36(3), 662–672. *(local)* Experiment 1's method and results were read.
- Pinet, S., Zielinski, C., Alario, F.-X. & Longcamp, M. (2022). *Typing Expertise in a Large Student Population.* Cognitive Research: Principles and Implications 7, 77. <https://pmc.ncbi.nlm.nih.gov/articles/PMC9356123/> Only the passages on letter-pair frequency were read.
- Brown, L. E., Rosenbaum, D. A. & Sainburg, R. L. (2003). *Limb Position Drift: Implications for Control of Posture and Movement.* Journal of Neurophysiology 90(5), 3105–3118. *(local)* The 4 cm figure is read off the paper's Figure 4C.
- Bangert, M. & Altenmüller, E. O. (2003). *Mapping Perception to Action in Piano Practice: A Longitudinal DC-EEG Study.* BMC Neuroscience 4, 26. <https://pmc.ncbi.nlm.nih.gov/articles/PMC270043/>
- Capio, C. M., Sit, C. H. P., Abernethy, B. & Masters, R. S. W. (2012). *The Possible Benefits of Reduced Errors in the Motor Skills Acquisition of Children.* Sports Medicine, Arthroscopy, Rehabilitation, Therapy & Technology 4, 1. *(local)* A review.
- Carter, C. E. & Grahn, J. A. (2016). *Optimizing Music Learning: Exploring How Blocked and Interleaved Practice Schedules Affect Advanced Performance.* Frontiers in Psychology 7, 1251. <https://pmc.ncbi.nlm.nih.gov/articles/PMC4989027/> Ten advanced clarinettists, mixed results; read and not used above.

**Abstract only**

- Ste-Marie, D. M., Clark, S. E., Findlay, L. C. & Latimer, A. E. (2004). *High Levels of Contextual Interference Enhance Handwriting Skill Acquisition.* Journal of Motor Behavior 36(1), 115–126. doi:10.3200/jmbr.36.1.115-126
- Capio, C. M., Poolton, J. M., Sit, C. H. P., Holmstrom, M. & Masters, R. S. W. (2013). *Reducing Errors Benefits the Field-Based Learning of a Fundamental Movement Skill in Children.* Scandinavian Journal of Medicine & Science in Sports 23(2), 181–188. doi:10.1111/j.1600-0838.2011.01368.x
- Guadagnoli, M. A. & Lee, T. D. (2004). *Challenge Point: A Framework for Conceptualizing the Effects of Various Practice Conditions in Motor Learning.* Journal of Motor Behavior 36(2), 212–224.
- Stambaugh, L. A. (2011). *When Repetition Isn't the Best Practice Strategy: Effects of Blocked and Random Practice Schedules.* Journal of Research in Music Education 58(4), 368–383. doi:10.1177/0022429410385945. Forty-one beginning clarinettists; random practice was faster at retention. Not used above.

**Known only as cited**

- Brady, F. (2004), the meta-analysis of contextual interference; through Czyż et al.
- Jarus, T. & Goverover, Y. (1999), Perceptual and Motor Skills 88, 437–447; through Graser et al. and ADR-024.
- Pollock, B. J. & Lee, T. D. (1997), Perceptual and Motor Skills 84(3), 851–858; through ADR-024.
- Rabbitt, P. M. A. (1968) and Pashler, H. & Baylis, G. (1991), on repetition effects; through Notebaert & Soetens.
- Behmer, L. P. & Crump, M. J. C., on typists' sensitivity to letter-pair frequency; through Pinet et al.
- The serial-reaction-time studies in ADR-024 § Research grounding (Journal of Cognition 2025; Scientific Reports 11, 2021).

**Wanted and not obtained**

- The full texts of Ste-Marie et al. (2004) and Capio et al. (2013). Paywalled; the developer tried each link on 2026-10-10.
- Duke, R. A., Simmons, A. L. & Cash, C. D. (2009), on how pianists practise. doi:10.1177/0022429408328851. Not read at all.
