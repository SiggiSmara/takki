"""ADR-027 § Milestone Ladder — the rung definitions, and the detector that
fires each rung once.

The definitions below are pure. Rungs 2 to 6 are a function of a layout and a
set of Known graphemes, and the `rest` rung of the landings and rest keys the
store holds. `satisfied_rungs` is a rolling query that can go down again.
`MilestoneDetector` is the edge between that query and the one-time event
ADR-027 § Key States calls a milestone.
"""

from collections.abc import Callable, Mapping, Sequence
from collections.abc import Set as AbstractSet

from takki import config
from takki.lesson.key_state import KeyStates
from takki.persistence import Landing, RestKey, Store
from takki.platform.layout import COL_TO_FINGER, Layout

REST = "rest"

# ADR-027 § Milestone Ladder: five evenly spaced sixths of the grapheme set
# above the `rest` rung. Hard-coded on purpose -- the fractions are the shape
# of the ladder, not a setting, and a profile whose "half the alphabet"
# milestone fired at a fifth would be a lie told to a child.
_FRACTIONS: tuple[tuple[str, int, int], ...] = (
    ("third", 1, 3),
    ("half", 1, 2),
    ("two_thirds", 2, 3),
    ("five_sixths", 5, 6),
    ("alphabet", 1, 1),
)

# Slugs are identifiers and are never spoken; the spoken name resolves through
# ADR-022's per-language YAML tier from Beta.
LADDER: tuple[str, ...] = (REST, *(slug for slug, _, _ in _FRACTIONS))

# The eight fingers that rest on keys (ADR-033). Thumbs are not taught.
FINGERS: frozenset[str] = frozenset(COL_TO_FINGER.values())


def grapheme_thresholds(layout: Layout) -> dict[str, int]:
    """How many Known graphemes each *counted* rung needs.

    The `rest` rung is deliberately absent. It is not a count of Known
    graphemes but where the fingers land (`rest_reached`), and a caller that
    compared a Known count against a `rest` entry would fire it off letters.
    Milestones are one-time and never revoked (ADR-027 § Key States), so the
    real rung could then never fire at all.
    """
    # ADR-027 § Milestone Denominator: typeable graphemes, not physical keys.
    # Composites count; the modifier that helps produce them does not.
    total = len(layout.graphemes)
    return {slug: total * num // den for slug, num, den in _FRACTIONS}


def satisfied_rungs(
    layout: Layout, known: AbstractSet[str], *, rest: bool = False
) -> tuple[str, ...]:
    """Which rungs the child has earned, in ladder order.

    `known` is the Known graphemes (ADR-027 § Key States); `rest` is whether
    the `rest` rung's criterion holds, which is read from the landings and the
    rest keys and cannot be read off a set of Known keys.
    """
    thresholds = grapheme_thresholds(layout)
    count = len(known & set(layout.graphemes))
    earned = [REST] if rest else []
    earned.extend(slug for slug, _, _ in _FRACTIONS if count >= thresholds[slug])
    return tuple(earned)


def rest_reached(
    first_rounds: Sequence[Landing],
    rest_keys: Sequence[RestKey],
    practice_days: Mapping[int, int],
    days: int = config.REST_SETTLED_SESSION_STARTS,
) -> bool:
    """ADR-027 § The `rest` rung — settled on `days` days, or the full round retired.

    `first_rounds` is every landing of a round 1, in the order pressed,
    `rest_keys` every rest key the profile has had, and `practice_days` each
    session's practice-day number. Only the current keys are read: a landing
    is judged against the key its finger has now.
    """
    current = {key.finger: key for key in rest_keys if key.replaced_at is None}
    # The full round retires when every rest key has passed its own test, and
    # after that no day has a complete first round, so the count would be
    # frozen for good. Retirement is the same judgement the rung makes.
    if all(finger in current and current[finger].passed_at is not None for finger in FINGERS):
        return True
    rounds: dict[int, list[Landing]] = {}
    for landing in first_rounds:
        rounds.setdefault(landing.session_id, []).append(landing)
    # One session start a day: a restart minutes later is not a cold start.
    # A round 1 cut short is passed over, and a later one the same day counts.
    # A session's day is its practice-day number, fixed when it started.
    starts: dict[int, list[Landing]] = {}
    for session_id, landings in rounds.items():
        if {landing.finger for landing in landings} >= FINGERS:
            starts.setdefault(practice_days[session_id], landings)
    latest = sorted(starts)[-days:]
    return len(latest) == days and all(_settled(starts[day], current) for day in latest)


def _settled(landings: Sequence[Landing], current: dict[str, RestKey]) -> bool:
    # A hand whose bump press missed has its landings unvalidated, so its
    # round fails; so does a finger with no current key.
    return all(
        landing.validated
        and (key := current.get(landing.finger)) is not None
        and (key.row, key.col) == (landing.row, landing.col)
        for landing in landings
    )


class MilestoneDetector:
    """ADR-027 § Milestone Ladder — fires each rung once, for one profile.

    `satisfied_rungs` is a rolling query over Known, and Known is derived and
    can go down (§ Key States). A milestone is a one-time event that is never
    revoked. This class is the edge between the two, and `Store` is what makes
    it idempotent: the `milestones` rows already written are the authority on
    what has fired, never an in-memory set.

    That choice is not about the store deduplicating writes -- `record_milestone`
    does that anyway. It is about `check`'s *return value*, which is the event
    a caller celebrates (ADR-010 § Milestone Levels). A detector that remembered
    in memory would start every session with an empty memory and hand back every
    rung the child has ever earned, so the child would be congratulated on a
    third of the alphabet every time the app opened. The rows outlive the
    session; the detector does not. The residual cost is the opposite ordering:
    the row is written before the caller speaks anything, so a crash in between
    loses the celebration and keeps the milestone. That is the right way round
    -- ADR-027 makes the stored row the milestone.
    """

    def __init__(
        self,
        store: Store,
        profile_id: int,
        layout: Layout,
        key_states: KeyStates,
        now: Callable[[], str] | None = None,
    ) -> None:
        self._store = store
        self._profile_id = profile_id
        self._layout = layout
        self._states = key_states
        # As in AttemptCounter: wall-clock UTC in the store's form (ADR-011),
        # a separate concern from Clock, which is monotonic. None leaves it to
        # the store.
        self._now = now

    def check(self) -> tuple[str, ...]:
        """Rungs earned since the last check, in ladder order, newly written.

        Costs one rolling-window query per Active grapheme, and one read of
        the first rounds until `rest` fires, so it belongs at a block or step
        boundary, not inside the prompt loop.

        A child can cross more than one rung between two checks -- a long gap,
        or a session that takes them from below `third` to past `half`. Every
        rung they crossed is written and returned, in ladder order; none is
        skipped for having been overtaken, because each is a thing that was
        earned. How a caller spaces two celebrations is its own problem.
        """
        achieved = set(self._store.achieved_milestones(self._profile_id))
        if not set(LADDER) - achieved:
            return ()
        earned = satisfied_rungs(
            self._layout,
            self._states.known_keys(),
            # Never re-measured once it has fired, which is the one-time half
            # of ADR-027's "on every check until it fires". Nothing writes
            # landings or rest keys until the alignment (alpha-plan #12m
            # session 7), so it cannot fire in a real session before then.
            rest=REST in achieved or self._rest_reached(),
        )
        newly = tuple(rung for rung in earned if rung not in achieved)
        timestamp = self._now() if self._now is not None else None
        for rung in newly:
            self._store.record_milestone(self._profile_id, rung, timestamp)
        return newly

    def _rest_reached(self) -> bool:
        return rest_reached(
            self._store.first_round_landings(self._profile_id),
            self._store.rest_keys(self._profile_id),
            self._store.practice_days_by_session(self._profile_id),
        )
