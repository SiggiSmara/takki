# ADR-033: Rest Keys and the Keyboard Alignment

**Status:** Accepted. Partly implemented: Stage 0 and the anchor bar are removed and the `rest` rung is built (alpha-plan #12m session 4, 2026-11-08); the new order and the slots are built (session (5), 2026-11-09); the alignment, the rest tier's states and the location rule are not. Of the amendments it requires, ADR-024's is made (2026-10-10), ADR-026's and ADR-011's (both 2026-11-01), ADR-032's and ADR-027's (both 2026-11-08), and ADR-010's, ADR-025's in part and ADR-023's in part (all 2026-11-08, session 4); the others are not.
**Date:** 2026-10-10
**Noted:** 2026-11-01 — alpha #13 answered § Work this ADR requires: the three Windows checks and the dead-key worry, from measurement. The answers are dated notes in that section, and none of them changes a decision here.

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

*(Note 2026-11-09, alpha-plan #12m session (5): the "Chosen" row holds only once the bump letters are had. Nothing is introduced until both index fingers are ready, and the bump letters come first ([ADR-032](0032-grapheme-led-introduction-and-selectable-ordering.md#the-strategy-takes-the-childs-rest-state), rest rule 1). Built.)*

**A cap on rounds per session**, about eight. **[S]** After it, fingers that are ready get keys and the others continue next session. If neither index finger is ready, no key is introduced that session.

*(Note 2026-11-09, alpha-plan #12m session (5): two readings, built as ADR-032 restates them. If only one index finger is ready, no key is introduced either: the bump letters come first, together, once both are ready (rest rule 1). And "fingers that are ready get keys" does not cover a finger's rest letter, which needs the finger only chosen, as the table above says (rest rule 3).)*

**A finger that keeps landing on different keys is asked which one it wants.** **[D]** It is answered by pressing the key, because there is no spoken yes or no to answer through. **[S]** It is asked when a finger has no chosen key at the cap. **[S]**

**Every later session starts with the child finding the bumps.** **[D]** The full round opens every session until the rest letters above the floor (next section) are learned. **[D]** A rest key below the floor, or with no letter, is judged by where the finger lands **[D]**, and passes when the landing is right at the first round of the last five sessions. **[S]** The full round retires when every rest key has passed its own test, strong ones by their letter being Known and the others by landing, and the opening then shrinks to the two bumps. **[S]** Retiring it when the strong letters alone are learned could leave a weak key never judged.

*(Note 2026-11-09, alpha-plan #12m session (5): decided by the developer, it also does not retire while any finger is not ready. Readiness is earned only in rounds, and a finger still not ready when the rounds stop would never get its other letters. This answers [ADR-032](0032-grapheme-led-introduction-and-selectable-ordering.md#open-questions) open question 6, and is built with the retirement in session (7). Session (7) also needs a rule for a finger that is chosen and never steady: it is not asked "which one do you want" again, since that is asked only of a finger with no chosen key, so the full round would run at every session start.)*

**Once the full round has retired, the child may retire the bumps as well, at any time after.** **[S]** This refines the first sentence of the paragraph above: finding the bumps opens every session until the child chooses otherwise, and that choice is not on offer while the full round still runs. The means waits for the "Takki key" ([roadmap § D](../roadmap.md#d-smaller-gaps-worth-a-line-in-the-relevant-adr)), as [ADR-024](0024-drill-content-and-lesson-granularity.md)'s "I know this one" probe does, and nothing of it is built before that exists. The child brings the bumps back the same way. Takki does not bring them back by itself: if `f` or `j` slips it is practised more, as any key is ([ADR-024](0024-drill-content-and-lesson-granularity.md#steady-state-drill-generation)). **[S]** After the bumps are retired, the only check left on the rest position is ordinary typing accuracy.

**If a child changes a rest key later**, keys already learned are left alone and later keys are described from the new one. **[S]** While the full round runs, a ready finger that lands on a different key three rounds in a row is asked the question again. After the full round has retired nothing observes those fingers, so a change comes only at the child's request, through the same way in as retiring the bumps. **[S]**

**What Takki cannot observe.** It sees which key was pressed after it asked for a finger. It does not see which finger pressed it, whether the hands left the keyboard, or whether the other fingers stayed in place. Every state above is a statement about keys pressed, taken on the assumption that the child did what was asked.

### Introduction order and slots

- **`f` and `j` are the first step and take no introduction slots.** **[D]** *(Note 2026-11-09, alpha-plan #12m session (5): built as written, decided by the developer when the reading was put to them. The bump letters are left out of the slot count, so a first day reaches `f j` and three steps after them, eight letters, which is what the rest-letter spike ran. Until then the code had counted them like any key.)*
- **After `f j`, each hand alternates between its most useful remaining letter and its next rest letter, useful first.** **[D]** A step is one letter per hand. "Most useful" is ADR-032's grapheme ranking, and its composite rules are unchanged. *(Note 2026-11-09, alpha-plan #12m session (5): the alternation is decided by a count: a hand's next letter is a strong rest letter when it has had more useful letters than strong rest letters. That is this alternation, except where one kind could not be taken for a while: the other kind then gets several turns in a row until the count evens out ([ADR-032 § Ordering C, restated](0032-grapheme-led-introduction-and-selectable-ordering.md#ordering-c-restated)). Built.)*
- **A rest letter takes an early turn only if its key carries at least a floor share of that language's key presses**: about 2%, configurable, computed from language data, with no per-language setting. **[D]** A rest letter above the floor is **strong** and one below it is **weak**. A weak rest letter comes at its ordinary rank. A hand's strong rest letters are taken strongest first, as the spike ran it. **[S]**
- **Which letters are rest letters is per child**, because the rest keys are. A child whose left middle finger rests on `e` has `e` as a rest letter and `d` as an ordinary one.
- **A letter on a finger that is not ready is passed over** for the hand's next letter on a finger that is. **[S]** *(Note 2026-11-09, alpha-plan #12m session (5): this does not cover the finger's rest letter, which needs the finger only chosen, as § The alignment's table says (ADR-032 rest rule 3). Built.)*
- **Rest letters other than `f` and `j` count against the slots.** **[D]**
- **A rest letter is introduced as every other letter is, with one difference in the script:** where another key is given a location, a rest letter is told "this is your rest key for that finger", or words to that effect. **[S]** This settles what the developer's earlier "shortened introduction" **[D]** covers. Only the script is shorter. The ramp-up is the ordinary one, and the ADR-024 amendment has to say what Phase B alternates a rest letter with, since it is itself the key its finger returns to. *(Note 2026-10-10: [ADR-024](0024-drill-content-and-lesson-granularity.md#the-ramp-up-restated-four-objectives-and-a-ladder-of-three-levels)'s ramp-up is now a ladder of levels and Phase B is gone. A rest letter, like the two bump letters, takes the ordinary ladder without its first level, Reach.)* *(Note 2026-11-09, alpha-plan #12m session (5b): the script is built. A bump letter: "It is the key with the bump, where that finger rests." Any other rest letter: "It is the key where that finger rests." Wording accepted by the developer; [ADR-023](0023-key-introduction-protocol.md#the-key-introduction-script) amended. The alignment's words in session (7) should use the same terms.)*
- **Every other key is located from its finger's rest key** ("one row up from where your middle finger rests"), which works whether or not the rest key carries a letter. **[S]** This replaces ADR-023's "closest known key on the same finger" and removes the wrong instruction [roadmap § D](../roadmap.md#d-smaller-gaps-worth-a-line-in-the-relevant-adr) records for `j`, which is told to reach from `f`. *(Note 2026-11-09, alpha-plan #12m session (5b): built, and ADR-023 amended ([§ The key introduction script](0023-key-introduction-protocol.md#the-key-introduction-script)). Spoken by the finger for every key, as this example has it, never by the rest key's letter: decided by the developer. A composite's modifier is located from its own finger's rest key, and a resumed step from today's rest keys.)*

**Six slots, with a new reason.** **[S]** [ADR-010](0010-lesson-structure-and-progression.md#the-introduction-gate-is-slots) set `MAX_KEYS_IN_PROGRESS` to six because Stage 0 had six keys. That reason is gone. Six is kept as three steps of one letter per hand on a first day, which is what the spike ran. It has no derivation beyond that and is to be tuned by ear.

**Standing against ADR-032.** **[S]** This order is Ordering C made concrete, with the alignment as its probe, and it becomes the default. Ordering A stays a selectable strategy and opens at the bump letters itself. Ordering C as ADR-032 sketched it was a round-robin across eight fingers seeded from the measured rest position; this order is per hand, so the ADR-032 amendment restates C and does not merely fill it in.

### Stage 0 is removed, and the first milestone changes

**Stage 0 is removed for every ordering.** **[S]** *(Removed from the code 2026-11-08, #12m session 4. Ordering A, still the default until session (5), opens at its own first pair, `f j`.)* Placing the hands does its work, and does it better: it starts from the landmark, it covers eight fingers where Stage 0 covered two, and it costs eight presses a round where Stage 0 cost several hundred prompts on letters that spell nothing. `r u v m` (the keys above and below the bumps) become ordinary letters.

Three things go with it and are named so that their amendments do not miss them:

- **The anchor bar is retired with it.** **[S]** [ADR-027 § The Anchor Gate](0027-key-and-accuracy-state-model.md#the-anchor-gate) goes as a whole: the `anchor` rung, the stricter bar (`ANCHOR_MIN_ATTEMPTS`, `ANCHOR_MIN_ACCURACY`), and the rule that holds `f` and `j` to it for the life of the profile. `f` and `j` are ordinary letters at the ordinary Known bar. The bar's validity was read off Stage 0's content, its reason was that every key was located from `f` or `j`, and keys are now located from each finger's own rest key. The rest position is checked by where fingers land, not by accuracy on two letters.
- **ADR-032 § Decision 2's "What Stage 0 already settles"** no longer holds: the first reach off the bumps is whatever the order's second step brings.
- **Reach-and-return is no longer a stage.** It is still practised: every key's ramp-up alternates it with a key the finger returns to ([ADR-024](0024-drill-content-and-lesson-granularity.md#new-key-ramp-up--four-phases)), and the alignment returns the hands to the bumps every round. *(Note 2026-10-10: under [ADR-024](0024-drill-content-and-lesson-granularity.md#the-ramp-up-restated-four-objectives-and-a-ladder-of-three-levels)'s ladder it is practised at the Reach level only, by a press of the finger's rest key after each reach. A rest letter and the bump letters have no reach and so no Reach level.)*

**The rest position is the ladder's first rung.** **[S]** It replaces the `anchor` rung with a new slug, `rest`. Criterion: all eight fingers land on their rest keys at the first round of each of the last five sessions. It reads session starts and not rounds within a session because of the Simon et al. result above and the developer's own statement that ingrained takes longer than two days.

*(Noted 2026-11-08, #12m session 4, which built the rung. [ADR-027 § The `rest` rung](0027-key-and-accuracy-state-model.md#the-rest-rung) reads this criterion differently in three places, each settled with the developer in the ADR-027 session:*
- *It counts **one session start a day**: the last five local days with a complete first round, and on each only the first such session. Five restarts in one sitting would pass "the last five sessions", and a restart minutes later is not cold.*
- *A landing is judged against the finger's **current** rest key, not the key current when it landed. A changed key restarts the count by itself, and the first day can count.*
- *It **also fires when the full round retires**, which otherwise could leave it unreachable for good.*

*Session 4 added how the day is read: from the round's UTC stamp, in the machine's zone, when the rung is checked; nothing local is stored (the developer's rule). A practice-day number per session replaces that in the next #12m session. Nothing writes landings or rest keys before session (7), so the rung cannot fire in a real session until then.)*

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

- **The layout tables hold only letters** ([layout.py](../../src/takki/platform/layout.py)), so `;` cannot be recognised as a rest key. The tables need every cell in the columns of the six fingers that are not index fingers (columns 1 to 3 and 8 to 13), whatever it carries. *(Done 2026-11-01, alpha-plan #12m session 1: the tables, the Windows reader, the dev stub and the fake return every cell of the scan-code grid. Keys that produce no character are not cells, so a press on one is still not a landing. [ADR-026 § Every cell of the grid](0026-platform-interface-abstraction.md#every-cell-of-the-grid) has what is in and out, and why.)*
- **A key that produces a character is already seen by the engine.** Any printable character reaches it as a character event, `;` included, so once the tables are filled a landing on such a key can be recognised. An earlier draft of this ADR said English could not recognise `;` before the key-capture work of alpha-plan #13 and #14. That was wrong: the gap is the table, not the capture.
- **The key's share of key presses needs a definition in the engine.** The spike counted a composite's presses toward each key it needs. The engine's `key_frequencies` was retired in alpha session 8c (ADR-032).
- **Spoken names for non-letter keys**, for the question "which one do you want", per language.
- **The lesson engine stays language-agnostic**: the floor is computed from language data and the bumps are positions.

**To check on Windows, in Alpha.** **[S]** The checks are Alpha work. If one turns up something that needs refining, the refinement may go to Beta. Which Windows sitting they join, alpha-plan #13's spikes or the #12h run, is the developer's call. Until a check says otherwise, a press on a key that produces no character is not a landing, and Takki guides the finger as it does for a press outside the column.

- **A landing on Enter, Backspace or Shift**, which produce no character and on the English keyboard sit in or beside the right little finger's columns.
- **Whether a resting finger can land on a key with side effects.** Caps Lock, Tab and Shift border the left little finger's column, and Enter and Backspace may fall inside the right little finger's.
- **That a held key is detected**, so that the "let go" instruction is spoken when it should be and not otherwise.

**A worry stored for the key-capture question.** **[S]** A dead key must be usable as a rest key, and today a landing on one cannot be recognised. Its press reaches the engine as a composing event that does not say which key it was, and it leaves a state armed that the next letter would inherit ([ADR-028](0028-composite-input-and-keyboard-ownership.md)). English has no dead key, so Alpha does not need this. It is to be answered when the key-capture source is decided, which the alpha plan has as #13 and #14, and it is noted in the #13 row. If it is not answered there it goes to Beta with the first dead-key language. Until then a press on a dead key is not a landing.

*Answered 2026-11-01 by alpha #13 ([research/key-capture-source.md](../research/key-capture-source.md) § 3; **[M]** measured, **[A]** argued).* Key events now come from Takki's own window ([ADR-028 § Event model](0028-composite-input-and-keyboard-ownership.md), "Decided").
- **A dead key's press arrives as a `KEYDOWN` naming the physical key by scan code**, with no character **[M]**: Icelandic `´` 52, German `^` 53.
- **It leaves compose state armed:** the next letter is composed with it, however long after **[M]**.
- **Takki can disarm it** by calling `ToUnicodeEx(VK_SPACE)` on the window's thread: 10 of 10 trials, after which the next letter arrives plain **[M]**. Leaving the window also disarms it (7 of 7) **[M]**.
- **A held dead key is armed or not by the parity of its presses** (6 of 6 holds) **[M]**. So the alignment disarms after *every* dead-key landing **[A]**. Lessons never do, because a composite must still compose.

So the worry does not go to Beta. Two parts still wait for the first dead-key language, because English has none:
- exposing the disarming call to the alignment, behind a Protocol ([ADR-019](0019-testing-strategy-and-io-isolation.md)). The call already exists as `_flush()` in `takki.platform.windows`, which the layout reader uses. It does what the spike did: Space through `ToUnicodeEx`, unflagged. It has to run on the window's thread, which is the main thread;
- recognising the landing.

*The three Windows checks above, spiked in alpha #13 (2026-11-01; [research/key-capture-source.md](../research/key-capture-source.md) § 7).*
- **Landing on Enter, Backspace, Shift, Tab or Caps Lock.** Each arrives as a `KEYDOWN`/`KEYUP` pair with its scan code and no character **[M]**. So the window *can* say which non-character key a finger landed on. "A press on a key that produces no character is not a landing" is now a choice for #12m to make, not a limit of the capture.
- **Side effects.**
  - **Caps Lock** changes only case, which is folded **[M]**.
  - **Tab** does nothing in Takki's window **[M]**.
  - **Left Shift pressed five times** opened the Sticky Keys box and took focus (one trial) **[M]**.
  - **Right Shift held about 8.5 s** opened the Filter Keys box and took focus (two trials) **[M]**.

  Both shortcuts are on by default, and both pause the lesson with a dialog the child cannot see. A resting little finger on Shift is exactly what triggers them.
- **A held key is caught in time.** The first OS repeat came 505–512 ms after the press **[M]**, long before Filter Keys' 8 s. pygame drops the repeat `KEYDOWN`s, though, and a non-character key has no `TEXTINPUT` to repeat. So "a repeat of a key that is still down" is visible for character keys only. For the alignment, a hold should be **a `KEYDOWN` with no `KEYUP` after a set time**, checked as a deadline every tick. That works for every key, Shift and Enter included, and does not depend on the user's repeat-delay setting **[A]**. #12m sets the time.

### Amendments this ADR requires

Each is a later session, one ADR per session.

| ADR | What changes |
|---|---|
| [ADR-023](0023-key-introduction-protocol.md) | § Stage 0 removed; the location rule reads from the rest key; the shortened script; open question 7 closed. **Location rule, script and open question 7 done 2026-11-09** (#12m session (5b)): [§ The key introduction script](0023-key-introduction-protocol.md#the-key-introduction-script), two amendments |
| [ADR-032](0032-grapheme-led-introduction-and-selectable-ordering.md) | Decision 2: no Stage 0 above the orderings; Ordering C restated as this order; the strategy takes the child's rest state; the key-share measure. **Done 2026-11-08** (alpha-plan #12m, the ADR-032 session): [ADR-032 § Decision 2 restated](0032-grapheme-led-introduction-and-selectable-ordering.md#decision-2-restated-rest-keys-and-ordering-c-as-the-default). It also retires Ordering B. It defines the key share asked for in § Work this ADR requires ("A key's share of key presses"). It differs from this ADR in five places, all recorded there: the bump letters, and so every letter, come once *both* index fingers are ready, which overrides § The alignment's "fingers that are ready get keys" when only one index finger is ready, and its table's "Chosen" row until the bump letters are had; with the engine's ranking, English's first steps after `f j` are `e n`, `a l`, `t o`, not § Consequences' `e o`, `a l`, `t i`, which was the spike's ranking; each hand's turn is decided by a count, which is the alternation of § Introduction order and slots except where one kind could not be taken for a while; and a rest letter needs its finger only chosen, as § The alignment's table says, so neither § Introduction order and slots' "a letter on a finger that is not ready is passed over" nor § The alignment's "fingers that are ready get keys" covers it *(2026-11-09, #12m session (5): the five differences have dated notes where they apply, and the order is built.)* |
| [ADR-027](0027-key-and-accuracy-state-model.md) | First rung is the rest position; § The Anchor Gate retired, with the anchor bar and the lifelong hold on `f` and `j`. **Done 2026-11-08** (alpha-plan #12m, the ADR-027 session): [ADR-027 § Rest keys, the ladder's presses and the `rest` rung](0027-key-and-accuracy-state-model.md#rest-keys-the-ladders-presses-and-the-rest-rung). It differs from this ADR's text in three places, all recorded there: the rung counts one session start a day, so "the last five sessions" in § Stage 0 is removed reads as the last five days; a landing is judged against the finger's current rest key; and the rung also fires when the full round retires, which otherwise could leave it unreachable. It also gives `f` and `j` a speed term of their own in Known. Dated notes in "The rest position is the ladder's first rung" are owed; #12m session (4) makes them. Whether a weak rest key's own test in § The alignment also reads days is put to the developer in session (7) |
| [ADR-010](0010-lesson-structure-and-progression.md) | "Why 6"; the first-rung row of the milestone table and its narrative note. **Done 2026-11-08** (alpha-plan #12m session 4). It leaves one reading open for session (5): § Introduction order and slots says `f` and `j` "take no introduction slots", and the code counts them in the slot gate like any key while they are not Known *(2026-11-09, session (5): the reading is closed. The developer decided `f` and `j` hold no slots, as § Introduction order and slots says, and the code now leaves them out of the count.)* |
| [ADR-024](0024-drill-content-and-lesson-granularity.md) | Phase B's same-finger anchor is the rest key, and what stands in when that key has no Active letter; the ramp-up of a rest letter; Stage 0's own content removed; the alignment's time is outside pace and block length; the block plan holds no key to the anchor bar. **Done 2026-10-10** (alpha-plan #12m): [ADR-024 § The ramp-up restated](0024-drill-content-and-lesson-granularity.md#the-ramp-up-restated-four-objectives-and-a-ladder-of-three-levels). This mark was added on 2026-11-08 |
| [ADR-011](0011-persistence-and-state.md) | The records in § What must be recorded; a landing has no latency. **Done 2026-11-01** (alpha-plan #12m session 2): [§ Records for the alignment, the rest keys and the ladder](0011-persistence-and-state.md#records-for-the-alignment-the-rest-keys-and-the-ladder). The records are in the store; nothing writes them until sessions (4), (6) and (7) |
| [ADR-028](0028-composite-input-and-keyboard-ownership.md), [ADR-005](0005-keyboard-handling.md) | A press in the alignment on a key that produces no character; a dead key as a rest key, with the key-capture decision |
| [ADR-026](0026-platform-interface-abstraction.md) | `get_layout_positions()` returns non-letter cells. **Done 2026-11-01** (alpha-plan #12m session 1): [§ Every cell of the grid](0026-platform-interface-abstraction.md#every-cell-of-the-grid) |
| [ADR-022](0022-localisation-strategy.md) | The alignment's strings: "press and let go", the "let go" instruction, finger guidance and non-letter key names |
| [ADR-012](0012-audio-feedback-design.md) | Feedback for a press that has no wrong answer |
| [ADR-025](0025-configuration-system.md) | The numbers above; `ANCHOR_MIN_ATTEMPTS` and `ANCHOR_MIN_ACCURACY` removed; rest keys as per-profile state. **Done in part 2026-11-08** (#12m session 4): the anchor numbers removed, `REST_SETTLED_SESSION_STARTS` added, rest keys recorded as state and not configuration. The other numbers are added by sessions (5) and (7), which read them |

[roadmap.md](../roadmap.md) (§ What is deliberately never taught, and the two § D items on the bump and on rest positions) and [architecture.md § Out of Scope](../architecture.md#out-of-scope) carry dated notes on the four tiers, added with this ADR.

### Consequences

- **Real words on the first day.** In the spike's English run the first three steps after `f j` are `e o`, `a l`, `t i`, and 38 words are typeable. Direction only. *(Note 2026-11-09, alpha-plan #12m session (5): that was the spike's ranking, by key share. The engine's ranking counts a letter once per word, and gives `e n`, `a l`, `t o` ([ADR-032 § Ordering C, restated](0032-grapheme-led-introduction-and-selectable-ordering.md#ordering-c-restated)), pinned by a `slow` test. How many words those make typeable was not counted.)*
- **The right little finger has a place in every language**, with or without a letter under it.
- **A session costs at least one round before any typing** while the full round runs, and the first session up to the cap. How long that takes is not measured. The cost falls to two presses when the full round retires, and to nothing if the child retires the bumps.
- **The introduction order becomes per child**, through rest letters and readiness. A strategy can no longer be computed from the layout and the language alone.
- **Phase B's fallback anchor becomes common.** A finger whose rest key has no letter, or a weak letter not yet introduced, has no same-finger letter to return to. ADR-032 open question 4 foresaw this for Orderings B and C. *(Note 2026-10-10: no longer a consequence. [ADR-024](0024-drill-content-and-lesson-granularity.md#the-ramp-up-restated-four-objectives-and-a-ladder-of-three-levels) has no Phase B, and the return is asked for by finger, so nothing has to stand in for a rest key without a letter.)*
- **The current code keeps Stage 0** until this is implemented. This document changes no code. *(Stage 0 removed from the code 2026-11-08, #12m session 4.)*

### Alpha, and the Windows re-validation run (#12h)

**Stage 0 is removed in Alpha, not in Beta.** **[S]** There is no point keeping what has been decided against. Alpha builds this ADR and makes its three Windows checks; only refinement that a check turns up may wait for Beta.

**#12h spends no time on what this ADR supersedes, unless the check answers something else that matters.** **[S]** Its check on the anchor rung is dropped: the rung and the anchor bar are retired. Its checks that were worded for Stage 0's keys are reworded for the new order when the run sheet is written. Recorded in the #12h row of [alpha-plan.md](../alpha-plan.md).

**Stage 0 is removed before #12h.** **[S]** Otherwise the run would test functionality that is replaced after it. #12h therefore waits for this ADR's amendments and its Alpha build, which are alpha-plan #12m, and hears the new first session. An earlier answer in the session, "the default order does not change before #12h", rested on the wrong claim about `;` corrected above and is withdrawn.

### Open questions

1. **For the pilot:** whether rest keys stay where they were chosen across sessions and as hands grow, and whether a child with a non-conventional rest key is slower to learn that finger's other keys. **[S]** Either could overturn this ADR.
