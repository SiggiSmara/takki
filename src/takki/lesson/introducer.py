from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from typing import Protocol

from takki.language import WordSource
from takki.lesson.key_state import KeyStates
from takki.platform.layout import (
    L_IDX,
    L_MID,
    L_PINK,
    L_RING,
    R_IDX,
    R_MID,
    R_PINK,
    R_RING,
    Layout,
    PhysicalKey,
)

HOME_ROW = 3
STAGE_0 = 0

# ADR-023 § Stage 0 and ADR-027 § The Anchor Gate name the same six keys, and
# both name them by position: (2,4) (3,4) (4,4) and (2,7) (3,7) (4,7), the two
# index home columns. Never a letter list -- German already differs at column 6
# and a layout session 12 reads may differ further out.
ANCHOR_COLUMNS: tuple[int, ...] = (4, 7)
# Home first: it carries the tactile bump and is the key every other position
# in the stage is described against. Then the reach up, then the reach down.
ANCHOR_ROWS: tuple[int, ...] = (HOME_ROW, 2, 4)

# ADR-023 § Phase 1: symmetric pairs by physical column, left member first.
# Column 4/7 stays in the table: the strategy is the complete home-row-fill
# order in its own right, and Stage 0 removes that pair by handing its keys
# over as already-had, not by the strategy knowing Stage 0 exists.
_PHASE1_COLUMN_PAIRS: tuple[tuple[int, int], ...] = ((4, 7), (3, 8), (2, 9), (1, 10), (5, 6))


def anchor_keys(layout: Layout) -> tuple[str, ...]:
    """Stage 0's six keys, in introduction order: f j r u v m on QWERTY."""
    # Indexed unguarded, unlike _phase1_slots' `if col in by_col`. That guard
    # implements an ADR-023 rule -- a home-row column with no letter gives a
    # solo step -- and there is no matching rule here: a Stage 0 of five keys
    # is not Stage 0, and a five-key anchor gate would quietly weaken ADR-027's
    # first rung. A layout that cannot supply these six positions is a broken
    # premise, so it fails loudly. Session 12 is where a real layout first
    # arrives; see its alpha-plan row.
    by_pos = {(key.row, key.col): name for name, key in layout.keys.items()}
    return tuple(by_pos[(row, col)] for row in ANCHOR_ROWS for col in ANCHOR_COLUMNS)


@dataclass(frozen=True)
class Location:
    """Where a new key sits relative to one the child already has."""

    reference: str
    row_delta: int  # negative = towards the number row
    col_delta: int  # negative = towards the left edge


@dataclass(frozen=True)
class KeyIntroduction:
    key: str  # physical key name: the character, or "dead-acute"/"altgr"
    finger: str
    side: str
    is_modifier: bool
    location: Location | None  # None only for the very first key introduced
    # "dead-key"/"altgr-chord" for a modifier, None for a direct-strike key.
    # ADR-028 § Modifier introduction wants the mechanism spoken; which script
    # a composite gets later (ADR-023) turns on the same value.
    mechanism: str | None


@dataclass(frozen=True)
class IntroductionStep:
    """One introduction step: one or two keys, left-hand member first.

    `phase` is 0 for Stage 0 (ADR-023 § Stage 0 — anchor establishment), then
    1 and 2 for the two phases of the default strategy.

    Two keys stay in one step because every consumer of the boundary treats the
    pair as a unit -- ADR-028's Phase A interleaves L-R-L-R, Phase B alternates
    four ways, the modifier branch is chosen by looking at both members, and
    ADR-012's encouragement line quotes the pair's combined coverage gain.
    """

    phase: int
    keys: tuple[KeyIntroduction, ...]


@dataclass(frozen=True)
class IntroductionSlot:
    """One step's worth of key names, before finger and location are worked out."""

    phase: int
    keys: tuple[str, ...]


class IntroductionStrategy(Protocol):
    """The introduction order *below* Stage 0 (ADR-023 § The introduction order
    is a swappable strategy).

    Returns every remaining slot in order, left-hand member first, and returns
    nothing that is already in `had`. Filtering is the strategy's job because
    pairing happens after it: a strategy that ignored `had` would mispair the
    survivors, not merely repeat itself.
    """

    def __call__(
        self, layout: Layout, source: WordSource, had: AbstractSet[str]
    ) -> list[IntroductionSlot]: ...


def home_row_fill(
    layout: Layout, source: WordSource, had: AbstractSet[str]
) -> list[IntroductionSlot]:
    """ADR-023's two-phase order: home row by symmetric pairs, then frequency
    leader per hand.

    The default, and the only ordering Alpha ships. The choice between it, an
    F/J-seeded order and a per-child calibrated one belongs to the Beta pilot
    (ADR-023 open question 6, roadmap B9) -- this seam exists so that choice
    costs a constructor argument rather than an engine rewrite.
    """
    slots = _phase1_slots(layout, had)
    running = set(had) | {name for slot in slots for name in slot.keys}
    slots.extend(_phase2_slots(layout, source, running))
    return slots


DEFAULT_STRATEGY: IntroductionStrategy = home_row_fill


class KeyIntroducer:
    """ADR-023's introduction sequence for one profile: Stage 0, then a strategy."""

    def __init__(
        self,
        layout: Layout,
        source: WordSource,
        key_states: KeyStates,
        strategy: IntroductionStrategy = DEFAULT_STRATEGY,
    ) -> None:
        self._layout = layout
        self._source = source
        self._states = key_states
        # A constructor argument rather than a config key or a profiles column:
        # the pilot A/Bs orderings per child, which is ADR-025's per-profile
        # tier, and that tier does not exist yet. A global config key would be
        # the wrong tier and would have to move; a schema column is out of
        # scope until there is something to store in it. The session loop (#11)
        # already holds one introducer per session and picks the strategy here.
        self._strategy = strategy
        # A key introduced but never answered has no key_stats row (ADR-027 §
        # First-Attempt Counting), so KeyStates cannot report it and the step
        # would repeat forever. This set is the only record that the script
        # already played, and it is deliberately session-local: see ADR-023 §
        # What the introducer remembers.
        self._introduced: set[str] = set()
        self._last_step: IntroductionStep | None = None

    def introduce_next(self) -> IntroductionStep | None:
        remaining = introduction_sequence(self._layout, self._source, self._had(), self._strategy)
        if not remaining:
            return None
        step = remaining[0]
        self._introduced.update(k.key for k in step.keys)
        self._last_step = step
        return step

    @property
    def last_step(self) -> IntroductionStep | None:
        # ADR-023: the child can re-hear the introduction script via the re-read key.
        return self._last_step

    def _had(self) -> set[str]:
        return self._states.active_keys() | self._introduced


def introduction_sequence(
    layout: Layout,
    source: WordSource,
    had: AbstractSet[str] = frozenset(),
    strategy: IntroductionStrategy = DEFAULT_STRATEGY,
) -> list[IntroductionStep]:
    """The remaining curriculum from `had`, in order. Pure: no store writes, no audio."""
    # key_stats is keyed by grapheme and this sequence by physical key, so a
    # composite the child has already typed arrives here as a name no layout
    # position exists for. Drop those rather than resolve them: a composite's
    # prerequisites are separate keys and carry their own rows.
    running = {name for name in had if name in layout.keys}
    steps: list[IntroductionStep] = []
    for slot in _stage0_slots(layout, running):
        steps.append(_build_step(layout, slot, running))
    # Stage 0's keys are ordinary curriculum keys as well -- f and j open the
    # default strategy's Phase 1, r v u m are Phase 2 keys -- so the strategy
    # is handed them in `had` and skips them. It is called after the loop
    # above, which is what puts them there.
    for slot in strategy(layout, source, running):
        steps.append(_build_step(layout, slot, running))
    return steps


def _stage0_slots(layout: Layout, had: AbstractSet[str]) -> list[IntroductionSlot]:
    """ADR-023 § Stage 0 — one row of the two index columns per step.

    Each step is a symmetric pair by physical position, exactly as Phase 1
    pairs are, so nothing downstream needs a second shape for the stage: the
    left-hand member is first and ADR-028's pair ramp-up reads off the step
    unchanged. What marks the stage is `phase`, which the drill generator
    needs anyway to pick Stage 0's own content.
    """
    by_pos = {(key.row, key.col): name for name, key in layout.keys.items()}
    slots: list[IntroductionSlot] = []
    for row in ANCHOR_ROWS:
        pending = tuple(name for col in ANCHOR_COLUMNS if (name := by_pos[(row, col)]) not in had)
        if pending:
            slots.append(IntroductionSlot(STAGE_0, pending))
    return slots


def _phase1_slots(layout: Layout, had: AbstractSet[str]) -> list[IntroductionSlot]:
    # Letters only. A modifier on the home row (Icelandic's dead-acute at col
    # 11) is not a location-anchoring exercise and has nothing to attach to
    # this early; it enters Phase 2 at its composite-frequency rank instead.
    by_col = {
        key.col: name
        for name, key in layout.keys.items()
        if key.row == HOME_ROW and not _is_modifier(layout, name)
    }
    slots: list[IntroductionSlot] = []
    paired: set[str] = set()
    for left, right in _PHASE1_COLUMN_PAIRS:
        members = tuple(by_col[col] for col in (left, right) if col in by_col)
        paired.update(members)
        pending = tuple(name for name in members if name not in had)
        if pending:
            slots.append(IntroductionSlot(1, pending))
    # ADR-023's "remaining row-3 letters solo" tail, outward by column so each
    # one anchors to the key introduced immediately before it.
    tail = (by_col[col] for col in sorted(by_col) if by_col[col] not in paired)
    slots.extend(IntroductionSlot(1, (name,)) for name in tail if name not in had)
    return slots


def _phase2_slots(
    layout: Layout, source: WordSource, had: AbstractSet[str]
) -> list[IntroductionSlot]:
    frequencies = source.key_frequencies(layout)
    pools: dict[str, list[str]] = {"L": [], "R": []}
    for name in sorted(frequencies, key=lambda n: (-frequencies[n], n)):
        if name not in had:
            pools[layout.keys[name].side].append(name)
    slots: list[IntroductionSlot] = []
    while pools["L"] or pools["R"]:
        leaders = tuple(pools[side].pop(0) for side in ("L", "R") if pools[side])
        slots.append(IntroductionSlot(2, leaders))
    return slots


def _build_step(layout: Layout, slot: IntroductionSlot, running: set[str]) -> IntroductionStep:
    introductions: list[KeyIntroduction] = []
    for name in slot.keys:
        introductions.append(_introduce(layout, name, running))
        # Added as we go, so the right-hand member of a pair may anchor to the
        # left-hand one the child has just been told about.
        running.add(name)
    return IntroductionStep(slot.phase, tuple(introductions))


def _introduce(layout: Layout, name: str, had: AbstractSet[str]) -> KeyIntroduction:
    key = layout.keys[name]
    return KeyIntroduction(
        key=name,
        finger=key.finger,
        side=key.side,
        is_modifier=_is_modifier(layout, name),
        location=_locate(layout, key, had),
        mechanism=_mechanism(layout, name),
    )


def _mechanism(layout: Layout, name: str) -> str | None:
    if not _is_modifier(layout, name):
        return None
    # None when a layout carries a modifier no grapheme depends on -- reachable
    # once session 12 reads real layouts. describe() then omits the mechanism
    # sentence, which is the honest output: there is nothing to explain.
    return next((g.mechanism for g in layout.graphemes.values() if name in g.prereq_keys), None)


def _locate(layout: Layout, key: PhysicalKey, had: AbstractSet[str]) -> Location | None:
    # A modifier produces no character and makes no sound of its own, so it is
    # never the anchor another key is described against -- it only receives one.
    candidates = [layout.keys[name] for name in had if not _is_modifier(layout, name)]
    if not candidates:
        return None
    same_finger = [other for other in candidates if other.finger == key.finger]
    reference = min(same_finger or candidates, key=lambda other: _distance(key, other))
    return Location(reference.name, key.row - reference.row, key.col - reference.col)


def _distance(key: PhysicalKey, other: PhysicalKey) -> tuple[int, int, str]:
    row_gap, col_gap = abs(key.row - other.row), abs(key.col - other.col)
    # Manhattan, then prefer the straight vertical reach: it is the motion the
    # finger already makes from its home position and the one that describes
    # itself by touch. Name last so ties never depend on dict order.
    return (row_gap + col_gap, col_gap, other.name)


def _is_modifier(layout: Layout, name: str) -> bool:
    return name not in layout.graphemes


# Placeholder English, in the style of focus_model's announcements. The real
# strings -- finger names, modifier names, example words -- are ADR-022's
# per-language YAML tier, which does not exist yet.
FINGER_NAMES: dict[str, str] = {
    L_PINK: "left little finger",
    L_RING: "left ring finger",
    L_MID: "left middle finger",
    L_IDX: "left index finger",
    R_IDX: "right index finger",
    R_MID: "right middle finger",
    R_RING: "right ring finger",
    R_PINK: "right little finger",
}

MODIFIER_NAMES: dict[str, str] = {
    "dead-acute": "the accent key",
    "altgr": "the right Alt key",
}

MECHANISM_NOTES: dict[str, str] = {
    "dead-key": "It will not make a sound on its own — it changes the next letter you press.",
    "altgr-chord": "Hold it down while you press another letter.",
}

_NUMBER_WORDS: tuple[str, ...] = ("zero", "one", "two", "three", "four")


def describe(introduction: KeyIntroduction) -> str:
    lead = "New key" if introduction.is_modifier else "New letter"
    name = (
        MODIFIER_NAMES.get(introduction.key, introduction.key)
        if introduction.is_modifier
        else _spoken(introduction.key)
    )
    parts = [f"{lead}: {name}.", f"Use your {FINGER_NAMES[introduction.finger]}."]
    if introduction.location is not None:
        parts.append(f"Reach {describe_location(introduction.location)}.")
    if introduction.mechanism is not None:
        # ADR-028 § Modifier introduction item 1: a modifier's announcement
        # carries the mechanism, or the child presses it and hears nothing.
        parts.append(MECHANISM_NOTES[introduction.mechanism])
    return " ".join(parts)


def describe_location(location: Location) -> str:
    moves: list[str] = []
    if location.row_delta:
        moves.append(
            f"{_count(location.row_delta, 'row')} {'up' if location.row_delta < 0 else 'down'}"
        )
    if location.col_delta:
        direction = "left" if location.col_delta < 0 else "right"
        moves.append(f"{_count(location.col_delta, 'position')} to the {direction}")
    return f"{' and '.join(moves)} from {_spoken(location.reference)}"


def _spoken(char: str) -> str:
    # German ß upper-cases to "SS", which would be read out as two letters.
    upper = char.upper()
    return upper if len(upper) == 1 else char


def _count(delta: int, noun: str) -> str:
    size = abs(delta)
    word = _NUMBER_WORDS[size] if size < len(_NUMBER_WORDS) else str(size)
    return f"{word} {noun}" if size == 1 else f"{word} {noun}s"
