# ADR-033: Rest Keys and the Keyboard Alignment

**Status:** Accepted. Not yet implemented, and the amendments it requires are not yet made.
**Date:** 2026-10-10

> Part of the [Takki architecture](../architecture.md).
> **Supersedes** [ADR-023](0023-key-introduction-protocol.md) § Stage 0. **Answers** ADR-023 open question 7 and [ADR-032](0032-grapheme-led-introduction-and-selectable-ordering.md) open question 2 (the probe Ordering C was waiting for).
> **Requires amendments** to ADR-023, ADR-032, ADR-027, ADR-010, ADR-024, ADR-011 and six others, listed in [§ Amendments this ADR requires](#amendments-this-adr-requires). None of them is made here. Until they are, those ADRs describe what the code does.

---

**Decision:** A finger's resting place is its own tier of key, separate from the letters the child types. Every session opens with the child finding the two bumps by touch and placing the other fingers, and where each finger lands, within its classical column, is that child's rest key. The opening shrinks as the position is learned, and in the end the child may drop it. Stage 0 is removed: placing the hands does its work. After the two bump letters, each hand alternates between its most useful remaining letter and the letter on its next rest key, so that real words come on the first day.

### How to read the marks

Every decision carries one of two marks.

- **[D]** Decided by the developer on 2026-10-10, before this ADR was written.
- **[S]** Settled with the developer in the session that wrote this ADR, the same day. Some of these were proposed by the previous session, some by this one and some by the developer in reply; all were put to the developer and accepted.

### Why this ADR exists

The aim is a blind child typing real words as early as possible.

[ADR-023 § Stage 0](0023-key-introduction-protocol.md#stage-0--anchor-establishment) opens the curriculum with six keys, `r f v` / `u j m` on QWERTY. Measured on the current generator with a child who answers every prompt correctly, those three steps take 675 prompts ([rampup-phases-practice-schedule.md](../research/rampup-phases-practice-schedule.md), § What the generator does today). The six keys spell nothing. Under Alpha's default order the first ten English keys spell one word in wordfreq's top 3000, `full`, and it is the eleventh key, `a`, that opens the first common ones.

Of the eight conventional "home" keys, only two can be found by touch: the keys with the moulded bumps. The other six are where fingers are told to rest, and a child's comfortable rest may not be on that row. ADR-023 open question 7 recorded the other half of the gap: nothing tells the child that fingers have resting places at all, and on US QWERTY the right little finger's conventional place is `;`, which is not a letter and so does not exist in the curriculum.

This ADR is decided **ahead of the Beta pilot** **[S]**. ADR-032 and [anchor-and-introduction-order.md](../research/anchor-and-introduction-order.md) both assigned the ordering to the pilot, and the note says its ADR amendment should be the pilot's output. The developer's reason for not waiting is that the choice shapes how the first keys are introduced at all, so there has to be one before there is anything to pilot. The pilot may still change it.

### Evidence, at its real strength

**No study tests a rest position chosen by the child's own landing**, for blind children or for anyone. The case for it is fit and comfort.

**It is not argued from learner choice.** [ADR-024 § Research grounding](0024-drill-content-and-lesson-granularity.md#research-grounding) records that choice-over-practice effects have largely failed to replicate. The earlier research note offered per-child calibration partly as "giving the child agency"; that argument is not used here.

What supports the design, each applied by analogy:

| Source | What it is | What it supports here |
|---|---|---|
| Brown, Rosenbaum & Sainburg (2003) | Five sighted adults, arm movements on an air sled with no touch landmark. Hand position drifted about 4 cm within a few movements while each movement's distance and direction stayed accurate | Returning to a landmark the hand can feel. It is why every session, and every round, starts from the bumps |
| Perkins School for the Blind | Practitioner guidance, not a study: "Usually, that position is on the home row, but really any consistent position to start from is fine" | That the conventional row is not required, only a consistent position |
| Simon, Lee & Cullen (2008) | 48 undergraduates learning number-pad sequences. Blocked practice gave 3.47% error in practice and 13.56% the next day | That a position steady within a session is not yet learned. It is why "ready" on day one is not the milestone |

All three are in [rampup-phases-practice-schedule.md](../research/rampup-phases-practice-schedule.md) or [references.md](../research/references.md).

The fit-and-comfort case rests on weaker material still: ergonomic keyboard makers offset columns by finger length, and one survey of school students found middle-finger length moderately correlated with typing speed ([anchor-and-introduction-order.md](../research/anchor-and-introduction-order.md) § Evidence). Both give a direction. Neither says which key a given child's finger should rest on, which is the reason to observe the landing and not assume it.

**The order was tried on 19 languages by a spike, and the spike is direction, not measurement** ([rest_letter_order_spike.py](../../spikes/rest_letter_order_spike.py), [results](../../spikes/results/rest_letter_order_results.txt)). Its word lists are unfiltered, 16 of its 19 layout tables were typed from memory and never checked against a keyboard, and it models only the conventional rest row, not a child's own. Within those limits:

- Taking every rest letter first costs more than half the typeable words on day one (mean ratio 0.45 to the plain most-useful order).
- Alternating with no floor falls behind after six steps in 15 of 19 languages (mean 0.81), because rest keys such as Spanish `k`, which carries no key presses, take turns from useful letters.
- Alternating with a 2% floor is about level with the plain order: mean 1.04 on day one, where it is behind in 9 languages and ahead in 3, and 1.03 after six steps, where it is behind in 2. It brings every strong rest key in by step 5.5 on average, against 6.8.

So the order in this ADR is **not justified by typeable words**. It costs little in words and brings the rest letters in sooner, and a rest letter needs no reach to be learned.

**Nothing here is decided on English alone.** In the spike's Greek table the right little finger rests on the accent dead key, which carries 10% of key presses; Spanish `k` carries none; French `m` is a rest key on AZERTY and costs words at the fourth step.

### Four tiers of key

A key can stand in four relations to the child, and the scope line in [roadmap § What is deliberately never taught](../roadmap.md) governs only the first. **[S]**

| Tier | What it is | Prompted | Counted | In a milestone denominator |
|---|---|---|---|---|
| 1. Typing target | A grapheme of the language | Yes, by character | Yes | Yes |
| 2. Pulled in by a target | A dead key or AltGr, announced inside the step of the first composite that needs it (ADR-032) | No | No | No |
| 3. Rest key | The place a finger rests | No | No | No |
| 4. Told about | Escape, and the deferred "Takki key" | No | No | No |

One physical key can be in more than one tier. `s` on QWERTY is a typing target and, for most children, a rest key. The Greek accent key is pulled in by a target and is a rest key.

This answers ADR-023 open question 7(a): naming a rest position is outside the scope line, as Escape is. `;` is still never a typing target.

### The rest tier

- **Each finger other than the index fingers gets a rest key. The child's own landing decides the row.** **[D]**
- **Fingers stay in their classical columns**, and Takki guides them there, so the standard finger-to-key map is unchanged. **[D]** A child whose middle finger rests on `e` still types `d` and `c` with that finger.
- **The index fingers rest on the bumps**, the keys at row 3, columns 4 and 7. **[D]** They are `f` and `j` on QWERTY-derived layouts and other letters elsewhere. This ADR writes `f j` for them as shorthand.
- **The bump is the one rest key the child does not choose.** **[S]** Every other rest key is selected by the child's landing. An index finger is never asked which key it wants, and its rest key cannot be changed.
- **Takki assumes the bumps are on those two keys.** **[S]** The known exception is Apple's keyboards from before its USB models, which put them on `d` and `k`; that is from keyboard-enthusiast sources and not an authoritative history. Takki runs on Windows, and no PC keyboard with the bumps elsewhere was found.
- **Thumbs are not taught.** **[D]**
- **The tier is the place.** A rest key is never prompted by character, never counted, and is in no milestone denominator. **[D]** *(Note 2026-10-10: [ADR-024](0024-drill-content-and-lesson-granularity.md#the-ramp-up-restated-four-objectives-and-a-ladder-of-three-levels)'s Reach level asks for a rest key during practice, by finger and not by character. The press is not counted, and unlike in the alignment a wrong key is rejected.)*
- **If a rest key carries a letter, that letter is an ordinary typing target as well**, by the ordinary rules. **[D]**
- **A rest key that is a modifier is treated as the semicolon is: it is a place to rest.** **[S]** It has no letter, so it is judged by where the finger lands. The modifier is taught on the typing side when a composite calls for it, by ADR-032's rule, which this ADR does not change. However many key presses the Greek accent key carries, it is not a rest letter and takes no early turn. A dead key is allowed as a rest key in every language; recognising a landing on one waits on the key-capture question (see [§ Work this ADR requires before it can be built](#work-this-adr-requires-before-it-can-be-built)).
- **A finger may land anywhere in its own column, and nowhere else.** **[S]** No row is ruled out and no further bound is set: the column is whatever the standard finger map gives that finger, which for the right little finger is columns 10 to 13. A press outside the column is answered with spoken guidance and is not recorded as a landing. **[S]**

### The alignment

The **alignment** is the child placing their hands. One **round** of it is eight prompted presses, one finger at a time. **[S]**

- **Order: index fingers on the bumps, then little fingers, then middle and ring.** **[D]** The bump and the little finger fix the hand's span, and the other two fall between them. **[S]**
- **The hands come off the keyboard between rounds, and Takki tells the child so.** **[S]** Takki cannot tell whether they did. It assumes it. The rest position is a tier of its own, so finding it is practised as a skill of its own, from off the keyboard each time.
- **No key is held down.** **[S]** The instruction for every press says to press the key and let go. If a key is held, Takki detects it and tells the child to let go, before it asks for the next finger. The signal is the one [ADR-027](0027-key-and-accuracy-state-model.md)'s held-key rule already reads: a repeat of a key that is still down. The landing itself stands, because holding a key does not change which key it was.
- **The bump press validates the hand.** **[S]** If the index finger's press is not the bump key, that hand's other presses in the round are not counted.
- **The alignment is not timed, and it does not affect the timing of anything after it.** **[S]** It is its own tier. No press in it has a latency, and how long it takes is charged to nothing that follows: not the child's pace, not the first prompt's latency, not a block's length, not session pacing.
- **There is no wrong answer** for the other six fingers. The key pressed is the finding. The reject-wrong-key model ([ADR-012](0012-audio-feedback-design.md)) does not apply, and no alignment press writes to `key_attempts` or `key_stats` or makes a key Active.

**The first session opens with a rest-position lesson: rounds repeated until the position is steady.** **[D]** Day one can be good enough to start keys. Ingrained takes longer than two days. **[D]**

**Two states per finger.** **[S]**

| State | Reached when | What it allows |
|---|---|---|
| **Chosen** | The finger lands on the same key on two rounds in a row, or the child picks a key in answer to the question below | The letter on that key may be introduced |
| **Ready** | The same key on three rounds in a row | The finger's other keys may be introduced |

An index finger is ready when it has found its bump on three rounds in a row. The split exists because a rest letter needs no reach, so it needs only a key, while every other key of the finger is described and reached from the rest key and needs that key to hold still.

**A cap on rounds per session**, about eight. **[S]** After it, fingers that are ready get keys and the others continue next session. If neither index finger is ready, no key is introduced that session.

**A finger that keeps landing on different keys is asked which one it wants.** **[D]** It is answered by pressing the key, because there is no spoken yes or no to answer through. **[S]** It is asked when a finger has no chosen key at the cap. **[S]**

**Every later session starts with the child finding the bumps.** **[D]** The full round opens every session until the rest letters above the floor (next section) are learned. **[D]** A rest key below the floor, or with no letter, is judged by where the finger lands **[D]**, and passes when the landing is right at the first round of the last five sessions. **[S]** The full round retires when every rest key has passed its own test, strong ones by their letter being Known and the others by landing, and the opening then shrinks to the two bumps. **[S]** Retiring it when the strong letters alone are learned could leave a weak key never judged.

**Once the full round has retired, the child may retire the bumps as well, at any time after.** **[S]** This refines the first sentence of the paragraph above: finding the bumps opens every session until the child chooses otherwise, and that choice is not on offer while the full round still runs. The means waits for the "Takki key" ([roadmap § D](../roadmap.md#d-smaller-gaps-worth-a-line-in-the-relevant-adr)), as [ADR-024](0024-drill-content-and-lesson-granularity.md)'s "I know this one" probe does, and nothing of it is built before that exists. The child brings the bumps back the same way. Takki does not bring them back by itself: if `f` or `j` slips it is practised more, as any key is ([ADR-024](0024-drill-content-and-lesson-granularity.md#steady-state-drill-generation)). **[S]** After the bumps are retired, the only check left on the rest position is ordinary typing accuracy.

**If a child changes a rest key later**, keys already learned are left alone and later keys are described from the new one. **[S]** While the full round runs, a ready finger that lands on a different key three rounds in a row is asked the question again. After the full round has retired nothing observes those fingers, so a change comes only at the child's request, through the same way in as retiring the bumps. **[S]**

**What Takki cannot observe.** It sees which key was pressed after it asked for a finger. It does not see which finger pressed it, whether the hands left the keyboard, or whether the other fingers stayed in place. Every state above is a statement about keys pressed, taken on the assumption that the child did what was asked.

### Introduction order and slots

- **`f` and `j` are the first step and take no introduction slots.** **[D]**
- **After `f j`, each hand alternates between its most useful remaining letter and its next rest letter, useful first.** **[D]** A step is one letter per hand. "Most useful" is ADR-032's grapheme ranking, and its composite rules are unchanged.
- **A rest letter takes an early turn only if its key carries at least a floor share of that language's key presses**: about 2%, configurable, computed from language data, with no per-language setting. **[D]** A rest letter above the floor is **strong** and one below it is **weak**. A weak rest letter comes at its ordinary rank. A hand's strong rest letters are taken strongest first, as the spike ran it. **[S]**
- **Which letters are rest letters is per child**, because the rest keys are. A child whose left middle finger rests on `e` has `e` as a rest letter and `d` as an ordinary one.
- **A letter on a finger that is not ready is passed over** for the hand's next letter on a finger that is. **[S]**
- **Rest letters other than `f` and `j` count against the slots.** **[D]**
- **A rest letter is introduced as every other letter is, with one difference in the script:** where another key is given a location, a rest letter is told "this is your rest key for that finger", or words to that effect. **[S]** This settles what the developer's earlier "shortened introduction" **[D]** covers. Only the script is shorter. The ramp-up is the ordinary one, and the ADR-024 amendment has to say what Phase B alternates a rest letter with, since it is itself the key its finger returns to. *(Note 2026-10-10: [ADR-024](0024-drill-content-and-lesson-granularity.md#the-ramp-up-restated-four-objectives-and-a-ladder-of-three-levels)'s ramp-up is now a ladder of levels and Phase B is gone. A rest letter, like the two bump letters, takes the ordinary ladder without its first level, Reach.)*
- **Every other key is located from its finger's rest key** ("one row up from where your middle finger rests"), which works whether or not the rest key carries a letter. **[S]** This replaces ADR-023's "closest known key on the same finger" and removes the wrong instruction [roadmap § D](../roadmap.md#d-smaller-gaps-worth-a-line-in-the-relevant-adr) records for `j`, which is told to reach from `f`.

**Six slots, with a new reason.** **[S]** [ADR-010](0010-lesson-structure-and-progression.md#the-introduction-gate-is-slots) set `MAX_KEYS_IN_PROGRESS` to six because Stage 0 had six keys. That reason is gone. Six is kept as three steps of one letter per hand on a first day, which is what the spike ran. It has no derivation beyond that and is to be tuned by ear.

**Standing against ADR-032.** **[S]** This order is Ordering C made concrete, with the alignment as its probe, and it becomes the default. Ordering A stays a selectable strategy and opens at the bump letters itself. Ordering C as ADR-032 sketched it was a round-robin across eight fingers seeded from the measured rest position; this order is per hand, so the ADR-032 amendment restates C and does not merely fill it in.

### Stage 0 is removed, and the first milestone changes

**Stage 0 is removed for every ordering.** **[S]** Placing the hands does its work, and does it better: it starts from the landmark, it covers eight fingers where Stage 0 covered two, and it costs eight presses a round where Stage 0 cost several hundred prompts on letters that spell nothing. `r u v m` (the keys above and below the bumps) become ordinary letters.

Three things go with it and are named so that their amendments do not miss them:

- **The anchor bar is retired with it.** **[S]** [ADR-027 § The Anchor Gate](0027-key-and-accuracy-state-model.md#the-anchor-gate) goes as a whole: the `anchor` rung, the stricter bar (`ANCHOR_MIN_ATTEMPTS`, `ANCHOR_MIN_ACCURACY`), and the rule that holds `f` and `j` to it for the life of the profile. `f` and `j` are ordinary letters at the ordinary Known bar. The bar's validity was read off Stage 0's content, its reason was that every key was located from `f` or `j`, and keys are now located from each finger's own rest key. The rest position is checked by where fingers land, not by accuracy on two letters.
- **ADR-032 § Decision 2's "What Stage 0 already settles"** no longer holds: the first reach off the bumps is whatever the order's second step brings.
- **Reach-and-return is no longer a stage.** It is still practised: every key's ramp-up alternates it with a key the finger returns to ([ADR-024](0024-drill-content-and-lesson-granularity.md#new-key-ramp-up--four-phases)), and the alignment returns the hands to the bumps every round. *(Note 2026-10-10: under [ADR-024](0024-drill-content-and-lesson-granularity.md#the-ramp-up-restated-four-objectives-and-a-ladder-of-three-levels)'s ladder it is practised at the Reach level only, by a press of the finger's rest key after each reach. A rest letter and the bump letters have no reach and so no Reach level.)*

**The rest position is the ladder's first rung.** **[S]** It replaces the `anchor` rung with a new slug, `rest`. Criterion: all eight fingers land on their rest keys at the first round of each of the last five sessions. It reads session starts and not rounds within a session because of the Simon et al. result above and the developer's own statement that ingrained takes longer than two days.

### What must be recorded

Alignment results need their own records, apart from `key_attempts`, which holds answers that can be wrong. The schema is the ADR-011 amendment's. The facts it must hold:

- **Each landing:** profile, session, round, finger, the physical position pressed (row and column, not a character), a UTC timestamp, and whether that hand's bump press validated it.
- **Each finger's rest key:** the position, when it was chosen and whether by landings or by answer, when it became ready, and when it passed its session-start test. Each of these is an event and gets its own column.
- **A changed rest key** keeps the old one, with when it was replaced.
- **The `rest` rung**, in `milestones`.

### Vocabulary

**Child-facing text says "rest", never "home".** **[D]** Strings are per-language YAML ([ADR-022](0022-localisation-strategy.md)).

**The ADRs keep "anchor" for the two bumps** and change only child-facing strings. **[S]** The word survives; the anchor bar and the anchor rung do not. The terms this ADR adds: **rest key** (the place), **rest letter** (the letter on it, a typing target), **rest position** (all eight), **alignment**, **round**, **landing**, **chosen**, **ready**, **strong** and **weak**.

### Numbers

Every number is configurable ([ADR-025](0025-configuration-system.md)) and none is per language. The names are suggestions.

| Name | Default | Mark |
|---|---|---|
| `REST_LETTER_MIN_SHARE` | 0.02 | [D] |
| `MAX_KEYS_IN_PROGRESS` | 6 | [S] |
| `ALIGNMENT_MAX_ROUNDS` | 8 | [S] |
| `REST_CHOSEN_ROUNDS` | 2 | [S] |
| `REST_READY_ROUNDS` | 3 | [S] |
| `REST_CHANGE_ROUNDS` | 3 | [S] |
| `REST_SETTLED_SESSION_STARTS` | 5 | [S] |

### Work this ADR requires before it can be built

**Alpha is built and checked on the English keyboard.** **[S]**

**To build, in Alpha.**

- **The layout tables hold only letters** ([layout.py](../../src/takki/platform/layout.py)), so `;` cannot be recognised as a rest key. The tables need every cell in the columns of the six fingers that are not index fingers (columns 1 to 3 and 8 to 13), whatever it carries.
- **A key that produces a character is already seen by the engine.** Any printable character reaches it as a character event, `;` included, so once the tables are filled a landing on such a key can be recognised. An earlier draft of this ADR said English could not recognise `;` before the key-capture work of alpha-plan #13 and #14. That was wrong: the gap is the table, not the capture.
- **The key's share of key presses needs a definition in the engine.** The spike counted a composite's presses toward each key it needs. The engine's `key_frequencies` was retired in alpha session 8c (ADR-032).
- **Spoken names for non-letter keys**, for the question "which one do you want", per language.
- **The lesson engine stays language-agnostic**: the floor is computed from language data and the bumps are positions.

**To check on Windows, in Alpha.** **[S]** The checks are Alpha work. If one turns up something that needs refining, the refinement may go to Beta. Which Windows sitting they join, alpha-plan #13's spikes or the #12h run, is the developer's call. Until a check says otherwise, a press on a key that produces no character is not a landing, and Takki guides the finger as it does for a press outside the column.

- **A landing on Enter, Backspace or Shift**, which produce no character and on the English keyboard sit in or beside the right little finger's columns.
- **Whether a resting finger can land on a key with side effects.** Caps Lock, Tab and Shift border the left little finger's column, and Enter and Backspace may fall inside the right little finger's.
- **That a held key is detected**, so that the "let go" instruction is spoken when it should be and not otherwise.

**A worry stored for the key-capture question.** **[S]** A dead key must be usable as a rest key, and today a landing on one cannot be recognised. Its press reaches the engine as a composing event that does not say which key it was, and it leaves a state armed that the next letter would inherit ([ADR-028](0028-composite-input-and-keyboard-ownership.md)). English has no dead key, so Alpha does not need this. It is to be answered when the key-capture source is decided, which the alpha plan has as #13 and #14, and it is noted in the #13 row. If it is not answered there it goes to Beta with the first dead-key language. Until then a press on a dead key is not a landing.

### Amendments this ADR requires

Each is a later session, one ADR per session.

| ADR | What changes |
|---|---|
| [ADR-023](0023-key-introduction-protocol.md) | § Stage 0 removed; the location rule reads from the rest key; the shortened script; open question 7 closed |
| [ADR-032](0032-grapheme-led-introduction-and-selectable-ordering.md) | Decision 2: no Stage 0 above the orderings; Ordering C restated as this order; the strategy takes the child's rest state; the key-share measure |
| [ADR-027](0027-key-and-accuracy-state-model.md) | First rung is the rest position; § The Anchor Gate retired, with the anchor bar and the lifelong hold on `f` and `j` |
| [ADR-010](0010-lesson-structure-and-progression.md) | "Why 6"; the first-rung row of the milestone table and its narrative note |
| [ADR-024](0024-drill-content-and-lesson-granularity.md) | Phase B's same-finger anchor is the rest key, and what stands in when that key has no Active letter; the ramp-up of a rest letter; Stage 0's own content removed; the alignment's time is outside pace and block length; the block plan holds no key to the anchor bar |
| [ADR-011](0011-persistence-and-state.md) | The records in § What must be recorded; a landing has no latency |
| [ADR-028](0028-composite-input-and-keyboard-ownership.md), [ADR-005](0005-keyboard-handling.md) | A press in the alignment on a key that produces no character; a dead key as a rest key, with the key-capture decision |
| [ADR-026](0026-platform-interface-abstraction.md) | `get_layout_positions()` returns non-letter cells |
| [ADR-022](0022-localisation-strategy.md) | The alignment's strings: "press and let go", the "let go" instruction, finger guidance and non-letter key names |
| [ADR-012](0012-audio-feedback-design.md) | Feedback for a press that has no wrong answer |
| [ADR-025](0025-configuration-system.md) | The numbers above; `ANCHOR_MIN_ATTEMPTS` and `ANCHOR_MIN_ACCURACY` removed; rest keys as per-profile state |

[roadmap.md](../roadmap.md) (§ What is deliberately never taught, and the two § D items on the bump and on rest positions) and [architecture.md § Out of Scope](../architecture.md#out-of-scope) carry dated notes on the four tiers, added with this ADR.

### Consequences

- **Real words on the first day.** In the spike's English run the first three steps after `f j` are `e o`, `a l`, `t i`, and 38 words are typeable. Direction only.
- **The right little finger has a place in every language**, with or without a letter under it.
- **A session costs at least one round before any typing** while the full round runs, and the first session up to the cap. How long that takes is not measured. The cost falls to two presses when the full round retires, and to nothing if the child retires the bumps.
- **The introduction order becomes per child**, through rest letters and readiness. A strategy can no longer be computed from the layout and the language alone.
- **Phase B's fallback anchor becomes common.** A finger whose rest key has no letter, or a weak letter not yet introduced, has no same-finger letter to return to. ADR-032 open question 4 foresaw this for Orderings B and C. *(Note 2026-10-10: no longer a consequence. [ADR-024](0024-drill-content-and-lesson-granularity.md#the-ramp-up-restated-four-objectives-and-a-ladder-of-three-levels) has no Phase B, and the return is asked for by finger, so nothing has to stand in for a rest key without a letter.)*
- **The current code keeps Stage 0** until this is implemented. This document changes no code.

### Alpha, and the Windows re-validation run (#12h)

**Stage 0 is removed in Alpha, not in Beta.** **[S]** There is no point keeping what has been decided against. Alpha builds this ADR and makes its three Windows checks; only refinement that a check turns up may wait for Beta.

**#12h spends no time on what this ADR supersedes, unless the check answers something else that matters.** **[S]** Its check on the anchor rung is dropped: the rung and the anchor bar are retired. Its checks that were worded for Stage 0's keys are reworded for the new order when the run sheet is written. Recorded in the #12h row of [alpha-plan.md](../alpha-plan.md).

**Stage 0 is removed before #12h.** **[S]** Otherwise the run would test functionality that is replaced after it. #12h therefore waits for this ADR's amendments and its Alpha build, which are alpha-plan #12m, and hears the new first session. An earlier answer in the session, "the default order does not change before #12h", rested on the wrong claim about `;` corrected above and is withdrawn.

### Open questions

1. **For the pilot:** whether rest keys stay where they were chosen across sessions and as hands grow, and whether a child with a non-conventional rest key is slower to learn that finger's other keys. **[S]** Either could overturn this ADR.
