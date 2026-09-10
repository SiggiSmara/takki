"""ADR-024 — Layer 1 drill content and lesson granularity.

Four phases of ramp-up after an introduction step, frequency-weighted bigrams
in steady state, one re-exposure slot with two triggers, and blocks sized by
the child's own pace. Pure logic: no store writes, no audio, no timers.
"""

import random
from collections import deque
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from enum import Enum, auto

from takki import config
from takki.clock import Clock
from takki.language import WordSource, sample_bigrams
from takki.lesson.introducer import (
    DIRECT,
    HOME_ROW,
    STAGE_0,
    IntroductionStep,
    KeyIntroduction,
    base_key,
    home_anchor_keys,
    key_distance,
)
from takki.lesson.key_state import KeyStates
from takki.platform.layout import Layout

# A unit is one bigram or short sequence, and each of its members is one prompt
# (ADR-027 § First-Attempt Counting: one attempt per prompt). A composite is a
# single prompt carrying two keystrokes, so a block's prompt count and its
# keystroke count are not the same number -- see the ADR-024 amendment.
Unit = tuple[str, ...]


class RampUpPhase(Enum):
    # ADR-024's Phase D is not here: it is the steady state, which is the
    # absence of a ramp-up rather than a fourth kind of one. A generator with
    # no ramp-up is in Phase D.
    A = auto()
    B = auto()
    C = auto()


@dataclass(frozen=True)
class DrillBlock:
    units: tuple[Unit, ...]

    @property
    def prompts(self) -> tuple[str, ...]:
        return tuple(prompt for unit in self.units for prompt in unit)


@dataclass
class _Member:
    """One step member's progress through the current phase.

    Thresholds are per-member, never shared (ADR-028 § Pair ramp-up: "a slow
    right hand cannot mask a poor left hand"), and `done` is sticky within a
    phase -- a member that met the bar keeps being prompted while its partner
    catches up, but does not lose what it earned by erring afterwards.
    """

    grapheme: str
    anchor: str | None
    streak: int = 0
    attempts: int = 0
    correct: int = 0
    rejections: int = 0
    done: bool = False


@dataclass
class RampUp:
    step: IntroductionStep
    phase: RampUpPhase
    members: tuple[_Member, ...]

    @property
    def graphemes(self) -> tuple[str, ...]:
        return tuple(member.grapheme for member in self.members)


class DrillGenerator:
    """Drill blocks for one session (ADR-024).

    Session-local, like the introducer's own record (ADR-023 § What the
    introducer remembers): the ramp-up phase is held here and nowhere else, so
    it does not survive the app closing. See the ADR-024 amendment for why, and
    for what happens to a child who was halfway through Phase B.
    """

    def __init__(
        self,
        layout: Layout,
        source: WordSource,
        key_states: KeyStates,
        clock: Clock,
        rng: random.Random,
    ) -> None:
        self._layout = layout
        self._source = source
        self._states = key_states
        self._clock = clock
        self._rng = rng
        self._ramp_up: RampUp | None = None
        # ADR-024 § Spaced re-exposure, session-time clock. A grapheme absent
        # here has not been practised this session, which reads as maximally
        # stale -- the first-block flood ADR-024 files as Beta scope. Switching
        # the anchor to `key_stats.last_practised_at` replaces this dict and
        # nothing else.
        self._last_practised: dict[str, float] = {}
        self._session_attempts: dict[str, int] = {}
        # Both derived tables are a full pass over the corpus, and the block
        # generator reads them several times per block.
        self._weights: dict[str, float] = source.grapheme_weights(layout)
        self._bigrams: dict[str, float] = dict(sorted(source.bigram_weights(layout).items()))
        self._pace: deque[tuple[int, float]] = deque(maxlen=config.PACE_BLOCKS)
        self._block_open = False
        self._paced_attempts = 0
        self._block_seconds = 0.0
        self._answered_at = 0.0

    @property
    def ramp_up(self) -> RampUp | None:
        return self._ramp_up

    @property
    def session_complete(self) -> bool:
        """ADR-024 § Per-key session floor — a soft signal, not an interrupt."""
        active = self._active()
        return bool(active) and all(
            self._session_attempts.get(name, 0) >= config.SESSION_KEY_FLOOR for name in active
        )

    def begin_step(self, step: IntroductionStep) -> None:
        """Start ADR-024's ramp-up for a step the introducer has just emitted."""
        if not 1 <= len(step.keys) <= 2:
            # ADR-028 § Pair ramp-up's branch table covers a solo member and a
            # pair, and is keyed off the step's contents. A step of another
            # shape is an amendment to that table, not something to guess at
            # here (ADR-032 raised the member-count/key-count split; the count
            # that matters to the table is the member count).
            raise ValueError(f"a step carries one or two graphemes, not {len(step.keys)}")
        members = tuple(_Member(intro.grapheme, self._anchor(intro, step)) for intro in step.keys)
        self._ramp_up = RampUp(step, RampUpPhase.A, members)

    def next_block(self) -> DrillBlock:
        now = self._clock.monotonic()
        if self._block_open:
            self._pace.append((self._paced_attempts, self._block_seconds))
        self._block_open = True
        self._paced_attempts = 0
        self._block_seconds = 0.0
        self._answered_at = now
        target = self._target_prompts()
        ramp = self._ramp_up
        if ramp is None:
            pool = self._pool(self._active())
            units = self._reexpose(self._steady_units(target, pool), pool)
        elif ramp.phase is RampUpPhase.C:
            units = self._phase_c_units(ramp, target)
        else:
            units = self._cycle_units(ramp, target)
        return DrillBlock(tuple(units))

    def record_attempt(self, grapheme: str, correct: bool) -> None:
        """One counted attempt, paired one-for-one with `AttemptCounter`'s.

        Called once per prompt the child answered, with the first press's
        outcome (ADR-027 § First-Attempt Counting). Retry presses are not
        attempts and must not reach here, or Phase C's accuracy would be
        measured over something that is not first-attempt accuracy.
        """
        now = self._clock.monotonic()
        # Pace is measured over the gaps between one answer and the next, and a
        # gap longer than the cap is not one of them -- the child had stopped
        # typing (a PAUSED interval, a walk-away, a conversation), and monotonic
        # time runs through all of those. Such an answer contributes neither
        # time nor count, so an interruption leaves the measured pace exactly
        # where it was instead of collapsing it. A block nobody answered
        # therefore contributes no sample at all rather than dead air.
        gap = now - self._answered_at
        self._answered_at = now
        if gap <= config.PACE_IDLE_GAP_SECONDS:
            self._block_seconds += gap
            self._paced_attempts += 1
        self._session_attempts[grapheme] = self._session_attempts.get(grapheme, 0) + 1
        self._last_practised[grapheme] = now
        ramp = self._ramp_up
        if ramp is None:
            return
        member = next((m for m in ramp.members if m.grapheme == grapheme), None)
        if member is None:
            # An anchor or a Phase C partner. It is practice, and it counts for
            # recency and the session floor, but the phase bar is the *new*
            # letter's (ADR-024 § New-key ramp-up).
            return
        self._count(member, ramp.phase, correct)
        if all(m.done for m in ramp.members):
            self._advance(ramp)

    # ---- ramp-up state -------------------------------------------------

    def _count(self, member: _Member, phase: RampUpPhase, correct: bool) -> None:
        if phase is RampUpPhase.A:
            # A streak: any wrong first press sends the child back to zero.
            member.streak = member.streak + 1 if correct else 0
            member.done = member.done or member.streak >= config.PHASE_A_STREAK
            return
        member.attempts += 1
        member.correct += 1 if correct else 0
        if phase is RampUpPhase.B:
            member.rejections += 0 if correct else 1
            if member.rejections > config.PHASE_B_MAX_REJECTIONS:
                # A run of 20 with an error budget of one, not a cumulative
                # count: spending the budget twice restarts the run. The two
                # counting models are ADR-024's own -- roadmap D "Phase A vs
                # Phase B counting" asks for them to be confirmed, not merged.
                member.attempts = member.correct = member.rejections = 0
            member.done = member.done or member.correct >= config.PHASE_B_ATTEMPTS
            return
        if member.attempts >= config.PHASE_C_ATTEMPTS:
            if member.correct / member.attempts >= config.PHASE_C_MIN_ACCURACY:
                member.done = True
            else:
                member.attempts = member.correct = 0

    def _advance(self, ramp: RampUp) -> None:
        following = {RampUpPhase.A: RampUpPhase.B, RampUpPhase.B: RampUpPhase.C}.get(ramp.phase)
        if following is None:
            self._ramp_up = None  # Phase D: the members join the steady-state pool.
            return
        ramp.phase = following
        for member in ramp.members:
            member.streak = member.attempts = member.correct = member.rejections = 0
            member.done = False

    def _remaining(self, member: _Member, phase: RampUpPhase) -> int:
        if member.done:
            return 0
        if phase is RampUpPhase.A:
            return config.PHASE_A_STREAK - member.streak
        if phase is RampUpPhase.B:
            return config.PHASE_B_ATTEMPTS - member.correct
        return config.PHASE_C_ATTEMPTS - member.attempts

    def _anchor(self, intro: KeyIntroduction, step: IntroductionStep) -> str | None:
        if intro.is_composite:
            # ADR-028 § Phase B: a composite's same-finger anchor is its own
            # base letter -- the same physical key with and without the
            # modifier gesture. Not a special case of the neighbour rule below,
            # a different rule.
            return intro.base
        key = base_key(self._layout, intro.grapheme)
        pool = self._active() - {member.grapheme for member in step.keys}
        # Direct graphemes only: an anchor is prompted like any other letter,
        # and a composite anchor would drag a second mechanism into the drill
        # the new key is supposed to have to itself.
        candidates = [
            self._layout.keys[name]
            for name in sorted(pool)
            if self._layout.graphemes[name].mechanism == DIRECT
        ]
        same_finger = [
            other for other in candidates if other.finger == key.finger and other.row == HOME_ROW
        ]
        same_hand = [other for other in candidates if other.side == key.side]
        reachable = same_finger or same_hand
        if not reachable:
            # Only Stage 0's first step gets here: f and j are the anchors, so
            # there is nothing behind them to alternate with. Phase A and B
            # fall back to the bare member, which for that step is the L-R
            # interleave the pair branch would have produced anyway.
            return None
        return min(reachable, key=lambda other: key_distance(key, other)).name

    # ---- content -------------------------------------------------------

    def _cycle(self, ramp: RampUp) -> tuple[Unit, ...]:
        if ramp.phase is RampUpPhase.A and ramp.step.stage != STAGE_0:
            # Phase A is pure repetition for a solo member, and the L-R
            # interleave for a pair (ADR-028 § Pair ramp-up).
            return tuple((member.grapheme,) for member in ramp.members)
        # Phase B's alternation, and Stage 0's Phase A as well: the stage
        # alternates each anchor with its own column reaches (f <-> r, f <-> v)
        # rather than repeating the reach, which is the whole reason plain
        # first-press accuracy is a valid anchor measure (ADR-027 § The Anchor
        # Gate). Ordinary Phase A repetition here would silently invalidate the
        # ladder's first rung.
        return tuple(
            (member.anchor, member.grapheme) if member.anchor else (member.grapheme,)
            for member in ramp.members
        )

    def _cycle_units(self, ramp: RampUp, target: int) -> list[Unit]:
        cycle = self._cycle(ramp)
        per_cycle = sum(len(unit) for unit in cycle)
        cycles = max(1, max(self._remaining(m, ramp.phase) for m in ramp.members))
        # Whole cycles only, so a pair's two members always get the same number
        # of prompts out of a block, and the block still ends on a unit
        # boundary (ADR-024 § Block boundaries).
        cycles = max(1, min(cycles, -(-target // per_cycle)))
        return [unit for _ in range(cycles) for unit in cycle]

    def _partners(self, ramp: RampUp) -> set[str]:
        # ADR-024 Phase C: "2-3 of the most-frequent previously-known keys".
        pool = self._active() - set(ramp.graphemes)
        ranked = sorted(pool, key=lambda name: (-self._weight(name), name))
        return set(ranked[: config.PHASE_C_PARTNERS])

    def _phase_c_units(self, ramp: RampUp, target: int) -> list[Unit]:
        # ADR-024 Phase C: the new letter mixed with 2-3 of the most frequent
        # letters the child already has, in 2- and 3-letter sequences chosen
        # for actual bigram frequency.
        partners = self._partners(ramp)
        # One alphabet per member -- {this letter} + partners, never the other
        # new letter. A pair step's two members are both brand new, and pairing
        # them with each other is the several-new-keys-at-once mix the ramp-up
        # exists to prevent (ADR-024 § New-key ramp-up).
        alphabets = {grapheme: self._pool({grapheme} | partners) for grapheme in ramp.graphemes}
        pools = {
            grapheme: {bigram: w for bigram, w in alphabet.items() if grapheme in bigram}
            for grapheme, alphabet in alphabets.items()
        }
        ranked = sorted(partners, key=lambda name: (-self._weight(name), name))
        fallback = ranked[0] if ranked else None
        rounds = max(1, max(self._remaining(m, ramp.phase) for m in ramp.members))
        units: list[Unit] = []
        count = 0
        for _ in range(rounds):
            if count >= target:
                break
            for member in ramp.members:
                unit = self._phase_c_unit(
                    member.grapheme, pools[member.grapheme], alphabets[member.grapheme], fallback
                )
                units.append(unit)
                count += len(unit)
        return units

    def _phase_c_unit(
        self,
        grapheme: str,
        pool: dict[str, float],
        alphabet: dict[str, float],
        fallback: str | None,
    ) -> Unit:
        if not pool:
            # The corpus has no bigram pairing this letter with any of its
            # partners -- a rare letter early in the curriculum. Alternate it
            # with the most frequent partner instead of dropping the phase.
            return (fallback, grapheme) if fallback else (grapheme,)
        bigram = self._choose(pool)
        unit: Unit = (bigram[0], bigram[1])
        if self._rng.random() < config.PHASE_C_TRIGRAM_CHANCE:
            unit = self._extend(unit, alphabet)
        return unit

    def _extend(self, unit: Unit, alphabet: dict[str, float]) -> Unit:
        # Grown in either direction, so a real trigram like "the" can come out
        # of "he" -- appending alone would only ever reach "het".
        options: dict[Unit, float] = {}
        for bigram, weight in alphabet.items():
            if bigram[1] == unit[0]:
                options[(bigram[0], *unit)] = weight
            if bigram[0] == unit[-1]:
                options[(*unit, bigram[1])] = weight
        if not options:
            return unit
        keys = sorted(options)
        return self._rng.choices(keys, weights=[options[key] for key in keys])[0]

    def _steady_units(self, target: int, pool: dict[str, float]) -> list[Unit]:
        # ADR-024 § Steady-state: frequency-weighted over the Active set, with
        # no comfort-class adjustment. Same-finger bigrams are practised, not
        # avoided -- they exist in the language and avoiding them is a debt
        # that comes due in Layer 2.
        count = max(1, -(-target // 2))
        if pool:
            return [(bigram[0], bigram[1]) for bigram in sample_bigrams(pool, count, self._rng)]
        # No corpus bigram over the Active set yet -- true for the first steps
        # of the curriculum, where the child has a handful of letters that never
        # co-occur. Pair single letters by their own frequency instead.
        active = sorted(self._active())
        if not active:
            # Nothing has been introduced yet. An empty block is the honest
            # answer -- the caller's next act is an introduction, and the same
            # state is what `session_complete` guards against.
            return []
        draws = self._weighted_draws(active, count * 2)
        return [(draws[i], draws[i + 1]) for i in range(0, len(draws), 2)]

    def _weighted_draws(self, active: list[str], count: int) -> list[str]:
        weights = [self._weight(name) for name in active]
        if sum(weights) <= 0:
            weights = [1.0] * len(active)
        return self._rng.choices(active, weights=weights, k=count)

    # ---- the re-exposure slot ------------------------------------------

    def _reexpose(self, units: list[Unit], pool: dict[str, float]) -> list[Unit]:
        """ADR-024's spaced re-exposure slot, with ADR-027's accuracy trigger.

        One mechanism, two triggers, and they are ordered rather than merged:
        a slipping anchor degrades every key position described against it, so
        it is served before a stale rare key. Each trigger replaces exactly one
        unit -- the most frequent ones, which the child meets again anyway --
        so block length is unchanged whether one fires, both, or neither.

        Ramp-up blocks are left alone. Their content is deliberately isolated
        (ADR-024 § New-key ramp-up), and a ramp-up is at most a few tens of
        prompts, so nothing waits long for its slot.
        """
        claims = self._claims(pool)
        if not claims:
            return units
        order = sorted(range(len(units)), key=lambda i: (-pool.get("".join(units[i]), 0.0), i))
        replaced = list(units)
        for claim, index in zip(claims, order, strict=False):
            replaced[index] = claim
        return replaced

    def _claims(self, pool: dict[str, float]) -> list[Unit]:
        claims: list[Unit] = []
        served: set[str] = set()
        for anchor in home_anchor_keys(self._layout):
            if not self._anchor_slipping(anchor):
                continue
            reach = self._reach(anchor)
            if reach is None:
                continue
            # A return-drill, not a repetition: the anchor prompt follows a
            # keystroke that took the finger off home, so the press measures
            # return-to-anchor accuracy (ADR-027 § The Anchor Gate).
            claims.append((reach, anchor))
            served.add(anchor)
        stale = self._stalest(served)
        if stale is not None:
            claims.append(self._stale_unit(stale, pool))
        return claims

    def _anchor_slipping(self, anchor: str) -> bool:
        stats = self._states.window_stats(anchor)
        # The same sample size the gate was measured over: below it a single
        # early slip would read as a lost anchor, and below it the child is
        # still inside Stage 0, where every block is anchor drill anyway.
        if stats.attempt_count < config.ANCHOR_MIN_ATTEMPTS:
            return False
        return stats.correct_count / stats.attempt_count < config.ANCHOR_MIN_ACCURACY

    def _reach(self, anchor: str) -> str | None:
        key = self._layout.keys[anchor]
        reaches = sorted(
            name
            for name in self._active()
            if self._layout.graphemes[name].mechanism == DIRECT
            and (other := self._layout.keys[name]).col == key.col
            and other.row != key.row
        )
        return self._rng.choice(reaches) if reaches else None

    def _stalest(self, served: AbstractSet[str]) -> str | None:
        now = self._clock.monotonic()
        stale = [
            name
            for name in self._active() - set(served)
            if now - self._last_practised.get(name, float("-inf")) > config.REEXPOSURE_STALE_SECONDS
        ]

        # Least recently practised first; among letters not practised at all
        # this session, the rarest, since those are the ones frequency-weighted
        # selection will not surface on its own.
        def staleness(name: str) -> tuple[float, float, str]:
            return (self._last_practised.get(name, float("-inf")), self._weight(name), name)

        return min(stale, key=staleness, default=None)

    def _stale_unit(self, grapheme: str, pool: dict[str, float]) -> Unit:
        carriers = {bigram: weight for bigram, weight in pool.items() if grapheme in bigram}
        if carriers:
            bigram = self._choose(carriers)
            return (bigram[0], bigram[1])
        others = sorted(self._active() - {grapheme}, key=lambda name: (-self._weight(name), name))
        # Name in the sort key, like every other selection here: zero-weight
        # graphemes exist by construction (`rank_graphemes`), so ties are
        # guaranteed, and without it they would resolve by set iteration order
        # and break reproducibility from the seed.
        return (grapheme, others[0] if others else grapheme)

    # ---- pace ----------------------------------------------------------

    def _target_prompts(self) -> int:
        # ADR-024 § Lesson granularity: target_keystrokes = target_seconds x
        # the child's rolling pace. Measured in prompts answered, which is what
        # the engine can count (ADR-027) and what the block is built out of.
        prompts = sum(count for count, _ in self._pace)
        seconds = sum(elapsed for _, elapsed in self._pace)
        if prompts == 0 or seconds <= 0:
            return config.FIRST_BLOCK_PROMPTS
        return max(1, round(config.BLOCK_TARGET_SECONDS * prompts / seconds))

    # ---- language layer ------------------------------------------------

    def _active(self) -> set[str]:
        # ADR-027 § Key States aligns the terminology: ADR-024's
        # "previously-known keys" are keys the child has been *introduced* to,
        # which is Active. Reading it as Known (90 attempts over 2 days) would
        # leave every early key without an anchor and never fire re-exposure.
        return self._states.active_keys() & set(self._layout.graphemes)

    def _weight(self, grapheme: str) -> float:
        return self._weights.get(grapheme, 0.0)

    def _pool(self, graphemes: AbstractSet[str]) -> dict[str, float]:
        # `self._bigrams` is sorted at construction so sampling is reproducible
        # from the seed alone, whatever order the source hands its weights in.
        return {
            bigram: weight for bigram, weight in self._bigrams.items() if set(bigram) <= graphemes
        }

    def _choose(self, pool: dict[str, float]) -> str:
        keys = sorted(pool)
        return self._rng.choices(keys, weights=[pool[key] for key in keys])[0]
