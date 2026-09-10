"""ADR-027 § Milestone Ladder — the rung definitions, the anchor gate's bar,
and the detector that fires each rung once.

The definitions below are pure: the ladder is a function of a layout and a set
of Known graphemes, and `satisfied_rungs` is a rolling query that can go down
again. `MilestoneDetector` is the edge between that query and the one-time
event ADR-027 § Key States calls a milestone.
"""

from collections.abc import Callable, Mapping
from collections.abc import Set as AbstractSet

from takki import config
from takki.lesson.introducer import anchor_keys
from takki.lesson.key_state import KeyStates, KnownCriterion, is_known
from takki.persistence import Store, WindowStats
from takki.platform.layout import Layout

ANCHOR = "anchor"

# ADR-027 § Milestone Ladder: five evenly spaced sixths of the grapheme set
# below the anchor gate. Hard-coded on purpose -- the fractions are the shape
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
LADDER: tuple[str, ...] = (ANCHOR, *(slug for slug, _, _ in _FRACTIONS))

# ADR-027 § The Anchor Gate: fewer repetitions than Known, at a higher accuracy
# bar. The day floor is Known's -- consolidation is the same mechanism either way.
ANCHOR_CRITERION = KnownCriterion(
    min_attempts=config.ANCHOR_MIN_ATTEMPTS,
    min_accuracy=config.ANCHOR_MIN_ACCURACY,
    min_distinct_days=config.KNOWN_MIN_DISTINCT_DAYS,
)

_NO_ATTEMPTS = WindowStats(attempt_count=0, correct_count=0, distinct_days=0)


def grapheme_thresholds(layout: Layout) -> dict[str, int]:
    """How many Known graphemes each *counted* rung needs.

    The anchor rung is deliberately absent. Its six keys are not a count of
    Known graphemes at the Known bar -- they are six named positions at the
    anchor bar (`anchor_reached`), and a caller that compared a Known count
    against a `{"anchor": 6}` entry would fire the anchor milestone off any six
    letters. Milestones are one-time and never revoked (ADR-027 § Key States),
    so the real gate could then never fire at all.
    """
    # ADR-027 § Milestone Denominator: typeable graphemes, not physical keys.
    # Composites count; the modifier that helps produce them does not.
    total = len(layout.graphemes)
    return {slug: total * num // den for slug, num, den in _FRACTIONS}


def satisfied_rungs(
    layout: Layout, known: AbstractSet[str], *, anchor: bool = False
) -> tuple[str, ...]:
    """Which rungs the child has earned, in ladder order.

    `known` is the Known graphemes (ADR-027 § Key States); `anchor` is whether
    Stage 0 was completed at the anchor bar, which is a separate measurement
    over a separate criterion and cannot be read off a set of Known keys.
    """
    thresholds = grapheme_thresholds(layout)
    count = len(known & set(layout.graphemes))
    earned = [ANCHOR] if anchor else []
    earned.extend(slug for slug, _, _ in _FRACTIONS if count >= thresholds[slug])
    return tuple(earned)


def anchor_reached(
    layout: Layout,
    stats: Mapping[str, WindowStats],
    criterion: KnownCriterion = ANCHOR_CRITERION,
) -> bool:
    """ADR-027 § The Anchor Gate — all six Stage 0 keys at the anchor bar.

    Plain first-press accuracy is a valid anchor measure because Stage 0
    alternates each anchor with its own column reaches, so every anchor prompt
    follows a keystroke that took the finger off home.

    Pure, and says nothing about *when* it is asked -- `MilestoneDetector`
    owns that, and its `_anchor_reached` is where the ADR's "once on stage
    completion" is reconciled with a bar that needs two calendar days.
    """
    return all(is_known(stats.get(name, _NO_ATTEMPTS), criterion) for name in anchor_keys(layout))


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
        # As in AttemptCounter: wall-clock ISO-8601 local time (ADR-011), a
        # separate concern from Clock, which is monotonic. None leaves it to
        # the store.
        self._now = now

    def check(self) -> tuple[str, ...]:
        """Rungs earned since the last check, in ladder order, newly written.

        Costs one rolling-window query per Active grapheme, so it belongs at a
        block or step boundary, not inside the prompt loop.

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
            # Never re-measured once it has fired. The anchor rung is the one
            # rung whose criterion is not a Known count, and the only one whose
            # window keeps moving under it after the stage that earned it.
            anchor=ANCHOR in achieved or self._anchor_reached(),
        )
        newly = tuple(rung for rung in earned if rung not in achieved)
        timestamp = self._now() if self._now is not None else None
        for rung in newly:
            self._store.record_milestone(self._profile_id, rung, timestamp)
        return newly

    def _anchor_reached(self) -> bool:
        """ADR-027 § The Anchor Gate, on the only cadence its own bar allows.

        The ADR says the rung fires "once on stage completion rather than as a
        rolling query", but the bar includes KNOWN_MIN_DISTINCT_DAYS -- so the
        instant Stage 0's last ramp-up ends is not a moment the gate can be
        evaluated at: a child who did the whole stage in one sitting fails it
        there, and under a literal reading would never be measured again. The
        gate is therefore evaluated on every check until it passes, and frozen
        after (the short-circuit in `check`).

        **This is open until roadmap § D closes, and it is a rolling query
        until then.** Two things follow that the ADR does not choose between.
        A child who ends Stage 0 just under the bar on one key fires the rung
        late, off a window that mixed drilling has since refilled -- which §
        Anchor accuracy is maintained says is still return-to-anchor accuracy
        ("once drills mix keys, virtually every f press already follows a
        different key"), and which § The Anchor Gate says must not happen
        ("ordinary drilling afterwards cannot dilute it"). Those two sentences
        disagree, and this method sides with the first because the second has
        no cadence that can satisfy the two-day floor. The visible cost is
        ladder order: a late anchor can fire after `third`. See the amendment
        in ADR-027 § The Anchor Gate.

        What this does *not* do is answer whether the curriculum may run ahead
        of the open gate (roadmap § D, "Does the curriculum wait for the anchor
        gate?"). That question has no owner yet and this detector reads the
        same either way -- which is why the rolling reading is the one that
        ships: closing the window at the end of Stage 0 would decide it here,
        by making the rung unreachable for any child the curriculum lets past.
        """
        return anchor_reached(
            self._layout,
            {name: self._states.window_stats(name) for name in anchor_keys(self._layout)},
        )
