"""ADR-024 § Ramp-up variability — the exit bars, and where a phase is recorded.

Two halves. The functions are pure: given one member's recent attempts they say
whether a bar has been met. `RampUpProgress` is the durable half: it reads and
writes the **phase completions**, because the bars cannot be re-derived from
`key_attempts` alone.

**Why a completion is recorded rather than re-derived.** `key_attempts` is a
200-row rolling window that is designed to forget (ADR-011). A first cut of this
module read every bar off that window, which meant a key drilled long enough for
the window to roll past its Phase A streak read as *back in Phase A* — on a key
the child had answered hundreds of times — and, because the session loop will
not introduce while a ramp-up is in progress, the curriculum could lock with
nothing able to release it. The mirror image was worse: a step could read as
complete for a child who had never met the bar. So a passed phase is an event
written once, and each phase's evidence is bounded by the *lifetime* attempt
count at its start, which no window can evict.

**Why the start is recorded as well.** A pair advances together (ADR-024), so a
member that passes first waits for its partner, and its next phase starts when
the *step* gets there. Read from its own completion, the presses it made while
waiting counted as evidence for a phase whose content it had not been given.
"""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from enum import Enum

from takki import config
from takki.lesson.key_state import key_speed
from takki.persistence import Attempt, Store


class RampUpPhase(Enum):
    # ADR-024's Phase D is not here: it is the steady state, which is the
    # absence of a ramp-up rather than a fourth kind of one. A generator with
    # no ramp-up is in Phase D. The values are what `ramp_up_phases.phase`
    # stores, so they are part of the schema and do not get renamed casually.
    A = "A"
    B = "B"
    C = "C"


PHASE_ORDER: tuple[RampUpPhase, ...] = (RampUpPhase.A, RampUpPhase.B, RampUpPhase.C)

# The most rows any bar can need: Phase C's window is the longest, and Phase B's
# run can be stretched by rejections, so a margin sits on top. Bounding the read
# keeps a keypress from pulling the whole 200-row window back out of SQLite.
EVIDENCE_ROWS = max(config.PHASE_A_STREAK, config.PHASE_B_ATTEMPTS, config.PHASE_C_ATTEMPTS) * 3


def trailing_streak(rows: Sequence[Attempt]) -> int:
    """Correct answers up to now, unbroken — Phase A's bar, and what it still owes."""
    run = 0
    for row in reversed(rows):
        if not row.correct:
            break
        run += 1
    return run


def live_run(
    rows: Sequence[Attempt],
    # Commented out 2026-10-07 (alpha-plan #12k, D2): no caller passed it.
    # max_rejections: int | None = None,
) -> int:
    """Phase B's count: correct answers since the miss that would overspend the budget."""
    # Back from the latest press, not forward from the phase's first. A forward
    # count pairs the misses up from wherever the read starts, so the capped
    # read and the full one disagreed about the same child (ADR-024).
    # budget = config.PHASE_B_MAX_REJECTIONS if max_rejections is None else max_rejections
    budget = config.PHASE_B_MAX_REJECTIONS
    correct = rejections = 0
    for row in reversed(rows):
        if row.correct:
            correct += 1
            continue
        rejections += 1
        if rejections > budget:
            break
    return correct


def bar_met(
    phase: RampUpPhase,
    evidence: Sequence[Attempt],
    baseline: float | None = None,
) -> bool:
    """Has this phase's bar been met over the attempts since the last one was?"""
    if phase is RampUpPhase.A:
        return trailing_streak(evidence) >= config.PHASE_A_STREAK
    if phase is RampUpPhase.B:
        return live_run(evidence) >= config.PHASE_B_ATTEMPTS
    recent = evidence[-config.PHASE_C_ATTEMPTS :]
    if len(recent) < config.PHASE_C_ATTEMPTS:
        return False
    if sum(row.correct for row in recent) / len(recent) < config.PHASE_C_MIN_ACCURACY:
        return False
    # Speed, read the way Known reads it and against the same baseline
    # (ADR-027 § Known has a speed term). No baseline, no bar -- by design: the
    # bump keys have none, and a term that failed closed would hold Stage 0
    # behind a measurement that cannot be made. A stretch with too few timed
    # answers is the same.
    observed = key_speed(recent)
    if baseline is None or observed is None:
        return True
    return observed <= baseline * config.PHASE_C_MAX_LATENCY_RATIO


def remaining(phase: RampUpPhase, evidence: Sequence[Attempt]) -> int:
    """Prompts this member still owes the current phase, for block sizing.

    Optimistic, exactly as the old counters were: an error simply means the next
    block carries the remainder (ADR-024 § Block boundaries). Never zero, or a
    block would be sized to nothing for a child who is still in the phase.
    """
    if phase is RampUpPhase.A:
        return max(1, config.PHASE_A_STREAK - trailing_streak(evidence))
    if phase is RampUpPhase.B:
        return max(1, config.PHASE_B_ATTEMPTS - live_run(evidence))
    # Phase C's bar reads the trailing thirty, so once thirty are in and the bar
    # is unmet, what is owed is another thirty rather than nothing -- the old
    # counters reset and handed out a full block, and the child who is missing
    # the bar is the one who needs the volume.
    owed = config.PHASE_C_ATTEMPTS - len(evidence)
    return owed if owed > 0 else config.PHASE_C_ATTEMPTS


@dataclass(frozen=True)
class MemberProgress:
    """One member's place in the ramp-up: the phase it has not yet passed, and its evidence."""

    grapheme: str
    phase: RampUpPhase | None
    evidence: tuple[Attempt, ...]
    attempts: int
    # False while the member waits for its partner: the step has not reached
    # `phase`, so there is no evidence and nothing is judged.
    begun: bool = True


class RampUpProgress:
    """Reads and records phase completions for one profile (ADR-024).

    The one place that decides what phase a member is in. It writes, which the
    drill generator deliberately does not: a completion is a durable fact about
    the child, in the same tier as an attempt row.
    """

    def __init__(self, store: Store, profile_id: int) -> None:
        self._store = store
        self._profile_id = profile_id

    def member(self, grapheme: str) -> MemberProgress:
        """Where this member stands, with only the rows its current phase can need."""
        records = self._store.phase_records(self._profile_id, grapheme)
        phase = next(
            (
                p
                for p in PHASE_ORDER
                if p.value not in records or records[p.value].completed_attempts is None
            ),
            None,
        )
        attempts = self._lifetime_attempts(grapheme)
        if phase is None:
            return MemberProgress(grapheme, None, (), attempts)
        record = records.get(phase.value)
        if record is None:
            return MemberProgress(grapheme, phase, (), attempts, begun=False)
        # Evidence starts where the step reached the phase, counted in lifetime
        # attempts so that an evicted row cannot move the boundary. Capped,
        # because a member that has sat in one phase for hundreds of attempts
        # needs only the recent ones -- every bar is a recent-N reading.
        since = attempts - record.started_attempts
        if since <= 0:
            # The phase has just begun and owns no attempts yet. Reading "the
            # last one row" here would hand the new phase the answer that
            # completed the previous one, so its bar would start one ahead.
            return MemberProgress(grapheme, phase, (), attempts)
        rows = self._store.window_attempts(
            self._profile_id, grapheme, limit=min(since, EVIDENCE_ROWS)
        )
        return MemberProgress(grapheme, phase, tuple(rows), attempts)

    def begin(self, progress: MemberProgress) -> MemberProgress:
        """The step has reached this member's phase: its evidence starts at this attempt."""
        assert progress.phase is not None
        self._store.begin_phase(
            self._profile_id, progress.grapheme, progress.phase.value, progress.attempts
        )
        return replace(progress, begun=True)

    def advance(self, progress: MemberProgress, baseline: float | None = None) -> bool:
        """Record a completion if this member's bar is now met. True when one was written."""
        if (
            progress.phase is None
            or not progress.begun
            or not bar_met(progress.phase, progress.evidence, baseline)
        ):
            return False
        self._store.record_phase(
            self._profile_id, progress.grapheme, progress.phase.value, progress.attempts
        )
        return True

    # Commented out 2026-10-07 (alpha-plan #12k, D1): no caller outside the
    # tests. `DrillGenerator._refresh_ramp` works the step's phase out itself.
    #
    # def step_phase(self, graphemes: Sequence[str]) -> RampUpPhase | None:
    #     """The step's phase: the least advanced member's, and None once all are done.
    #
    #     A pair advances together and every bar is per-member (ADR-024 § A pair
    #     advances phase together), so the slower member sets the phase. Because a
    #     completion is written once, a member that has finished stays finished --
    #     the stickiness the old in-memory `done` flag had.
    #     """
    #     reached = [p for p in (self.member(name).phase for name in graphemes) if p is not None]
    #     return min(reached, key=PHASE_ORDER.index) if reached else None

    def _lifetime_attempts(self, grapheme: str) -> int:
        # `key_stats` is the lifetime counter and never forgets, which is why the
        # phase boundaries are expressed in it rather than in window positions.
        stat = self._store.key_stats(self._profile_id).get(grapheme)
        return stat.attempt_count if stat is not None else 0
