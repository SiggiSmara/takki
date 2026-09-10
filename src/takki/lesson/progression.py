"""ADR-010 § Progression Rules — the thresholds that pace the curriculum.

Rolling queries over key state, answered whenever the session loop asks. None
of these is a milestone: no rung, no `milestones` row, no one-time event. A
predicate here can read True today, False tomorrow and True again the day
after — which is what a progression gate is, and exactly what a milestone is
not (ADR-027 § Key States). That is the whole reason they are not in
`takki.lesson.milestones`: same state, opposite lifetime.

Counted over **Active** graphemes, not Known. ADR-010's own wording for the
Layer-2 unlock is "≥ 8 keys known", but it predates ADR-027's vocabulary and
both later ADRs read it as Active — ADR-027 § Milestone Ladder ("ADR-010
unlocks Layer 2 at ≥ 8 Active keys") and ADR-028 § Layer-2 unlock, whose walk
of the English count moves it by two per introduction step, which Known cannot
do: Known needs 90 attempts across two calendar days.
"""

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


def ready_for_new_key(
    layout: Layout,
    states: KeyStates,
    min_presses: int = config.INTRODUCE_MIN_PRESSES,
    min_accuracy: float = config.INTRODUCE_MIN_ACCURACY,
) -> bool:
    """ADR-010: a new key arrives once accuracy on the *current set* holds up.

    Aggregate, not per key: ADR-010 says "first-attempt accuracy on current
    keys ... over a minimum of 50 presses" and ADR-023 § Where the phase
    boundary is restates it as "on the current set", so the rolling windows of
    every Active grapheme are summed and one accuracy is taken over the total.
    A per-key reading would be a second, stricter definition of Known, which is
    the trap ADR-023 names in that same section.

    An empty Active set is ready. There is nothing to be accurate on before the
    first key, and a gate that needed 50 presses to open would never let the
    first one through.

    This is one of the two gates on introducing a key, not the gate. ADR-024's
    ramp-up is the other, and it is the drill generator's: the loop asks the
    introducer for a step when the current step's ramp-up has ended *and* this
    predicate holds.

    **It goes slack as the set matures, and that is the aggregate reading's
    price.** Each key's window is capped at ATTEMPT_WINDOW, so at ten Active
    keys one brand-new key at 33% moves a set sitting at 98% by about a point
    -- the gate stays open and only the ramp-up is pacing anything. The
    alternative readings are worse or cost more: a per-key floor is the one
    ADR-023 rejects by name (89% on one home-row key would lock the curriculum
    with nothing able to release it), and "the last 50 presses across the set"
    -- arguably the better reading of ADR-010's sentence -- needs a cross-key
    recent-N query that `Store` does not have. Filed in roadmap § D.
    """
    active = active_graphemes(layout, states)
    if not active:
        return True
    windows = [states.window_stats(name) for name in active]
    attempts = sum(window.attempt_count for window in windows)
    if attempts < min_presses:
        return False
    # `>=`, where ADR-010's prose says "exceeds". Every bar in the engine is a
    # floor the child may land exactly on -- Known, the anchor gate, Phase C --
    # and the two readings differ only at exactly 90.000%.
    return sum(window.correct_count for window in windows) / attempts >= min_accuracy
