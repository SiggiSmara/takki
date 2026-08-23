"""ADR-027 § Milestone Ladder — the rung definitions and the anchor gate's bar.

Definition only. Detecting that a rung has been reached, writing the
`milestones` row and firing once are session 10's; nothing here touches a
store, and the ladder is a function of a layout and a set of Known graphemes.
"""

from collections.abc import Mapping
from collections.abc import Set as AbstractSet

from takki import config
from takki.lesson.introducer import anchor_keys
from takki.lesson.key_state import KnownCriterion, is_known
from takki.persistence import WindowStats
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

    Evaluated once, on Stage 0 completion, over the stage's own rolling-window
    stats. Plain first-press accuracy is a valid anchor measure because Stage 0
    alternates each anchor with its own column reaches, so every anchor prompt
    follows a keystroke that took the finger off home.
    """
    return all(is_known(stats.get(name, _NO_ATTEMPTS), criterion) for name in anchor_keys(layout))
