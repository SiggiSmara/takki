"""ADR-010 § Progression Rules — the thresholds that pace the curriculum.

Rolling queries over key state, answered whenever the session loop asks. None
of these is a milestone: no rung, no `milestones` row, no one-time event. A
predicate here can read True today, False tomorrow and True again the day
after — which is what a progression gate is, and exactly what a milestone is
not (ADR-027 § Key States). That is the whole reason they are not in
`takki.lesson.milestones`: same state, opposite lifetime.

The Layer-2 unlock is counted over **Active** graphemes, not Known; the slot
gate is what counts Active-but-not-Known. ADR-010's own wording for the
Layer-2 unlock is "≥ 8 keys known", but it predates ADR-027's vocabulary and
both later ADRs read it as Active — ADR-027 § Milestone Ladder ("ADR-010
unlocks Layer 2 at ≥ 8 Active keys") and ADR-028 § Layer-2 unlock, whose walk
of the English count moves it by two per introduction step, which Known cannot
do: Known needs 90 attempts across two calendar days.
"""

from collections.abc import Iterable

from takki import config
from takki.lesson.key_state import KeyStates
from takki.platform.layout import Layout


def active_graphemes(layout: Layout, states: KeyStates) -> set[str]:
    """The child's Active set, restricted to what this layout can produce.

    `key_stats` survives a profile's language change, so the raw Active set can
    carry characters the current keyboard has no key for. The same restriction
    the milestone denominator applies (ADR-027 § Milestone Denominator).
    """
    return states.active_keys() & set(layout.graphemes)


def layer_two_unlocked(
    layout: Layout,
    states: KeyStates,
    minimum: int = config.LAYER_2_MIN_KEYS,
) -> bool:
    """ADR-010: real words unlock at ≥ 8 keys, checked after each introduction step."""
    return len(active_graphemes(layout, states)) >= minimum


def keys_in_progress(layout: Layout, states: KeyStates) -> set[str]:
    """The keys holding a slot: introduced and practised, not yet Known."""
    return active_graphemes(layout, states) - states.known_keys()


def room_for_step(
    layout: Layout,
    states: KeyStates,
    graphemes: Iterable[str],
    cap: int = config.MAX_KEYS_IN_PROGRESS,
) -> bool:
    """ADR-010: a step is introduced only if it leaves at most `cap` keys in progress."""
    in_progress = keys_in_progress(layout, states)
    if not in_progress:
        # Always room, whatever the cap: one below the first step's size would
        # otherwise never let it through.
        return True
    # A union, so a member that is already Active is not counted twice.
    return len(in_progress | set(graphemes)) <= cap
