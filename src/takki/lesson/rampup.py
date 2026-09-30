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
count at the previous completion, which no window can evict.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import Enum
from statistics import median

from takki import config
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
    max_rejections: int | None = None,
) -> int:
    """Correct answers in the run in progress, which a second rejection restarts.

    Phase B's counting model, not Phase A's (ADR-024, and roadmap D "Phase A vs
    Phase B counting", which asks for the two models to be confirmed rather than
    merged). The *live* run, not the best one ever seen: a child who spends the
    budget twice is starting again, and a block sized off their old best run
    would be sized for progress they no longer have.
    """
    budget = config.PHASE_B_MAX_REJECTIONS if max_rejections is None else max_rejections
    correct = rejections = 0
    for row in rows:
        if row.correct:
            correct += 1
            continue
        rejections += 1
        if rejections > budget:
            correct = rejections = 0
    return correct


def median_latency(rows: Iterable[Attempt]) -> float | None:
    """Median measured latency, or None when nothing in the window was measured."""
    measured = [row.latency_ms for row in rows if row.latency_ms is not None]
    return median(measured) if measured else None


def baseline_latency(windows: Iterable[Sequence[Attempt]]) -> float | None:
    """ADR-027: the child's own reference, pooled over their Known keys' windows."""
    return median_latency(row for window in windows for row in window)


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
    # Speed, against the child's own baseline. No baseline, no bar -- by design:
    # every profile's first days have no Known key, Stage 0 included, so a term
    # that failed closed would hold the whole curriculum behind a measurement
    # that cannot yet be made (ADR-027 § The latency baseline). An unmeasured
    # stretch is the same: ADR-011 gives NULL exactly one meaning.
    observed = median_latency(recent)
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
    """One member's place in the ramp-up: the phase it is in, and that phase's evidence."""

    grapheme: str
    phase: RampUpPhase | None
    evidence: tuple[Attempt, ...]
    attempts: int


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
        done = self._store.completed_phases(self._profile_id, grapheme)
        phase = next((p for p in PHASE_ORDER if p.value not in done), None)
        attempts = self._lifetime_attempts(grapheme)
        if phase is None:
            return MemberProgress(grapheme, None, (), attempts)
        # Evidence starts where the previous phase ended, counted in lifetime
        # attempts so that an evicted row cannot move the boundary. Capped,
        # because a member that has sat in one phase for hundreds of attempts
        # needs only the recent ones -- every bar is a recent-N reading.
        since = attempts - done.get(self._previous(phase), 0)
        if since <= 0:
            # The phase has just begun and owns no attempts yet. Reading "the
            # last one row" here would hand the new phase the answer that
            # completed the previous one, so its bar would start one ahead.
            return MemberProgress(grapheme, phase, (), attempts)
        rows = self._store.window_attempts(
            self._profile_id, grapheme, limit=min(since, EVIDENCE_ROWS)
        )
        return MemberProgress(grapheme, phase, tuple(rows), attempts)

    def advance(self, progress: MemberProgress, baseline: float | None = None) -> bool:
        """Record a completion if this member's bar is now met. True when one was written."""
        if progress.phase is None or not bar_met(progress.phase, progress.evidence, baseline):
            return False
        self._store.record_phase(
            self._profile_id, progress.grapheme, progress.phase.value, progress.attempts
        )
        return True

    def step_phase(self, graphemes: Sequence[str]) -> RampUpPhase | None:
        """The step's phase: the least advanced member's, and None once all are done.

        A pair advances together and every bar is per-member (ADR-024 § A pair
        advances phase together), so the slower member sets the phase. Because a
        completion is written once, a member that has finished stays finished --
        the stickiness the old in-memory `done` flag had.
        """
        reached = [p for p in (self.member(name).phase for name in graphemes) if p is not None]
        return min(reached, key=PHASE_ORDER.index) if reached else None

    def _previous(self, phase: RampUpPhase) -> str:
        index = PHASE_ORDER.index(phase)
        return PHASE_ORDER[index - 1].value if index else ""

    def _lifetime_attempts(self, grapheme: str) -> int:
        # `key_stats` is the lifetime counter and never forgets, which is why the
        # phase boundaries are expressed in it rather than in window positions.
        stat = self._store.key_stats(self._profile_id).get(grapheme)
        return stat.attempt_count if stat is not None else 0
