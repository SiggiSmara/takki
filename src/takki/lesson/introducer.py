from collections.abc import Set as AbstractSet
from dataclasses import dataclass

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

# ADR-023 § Phase 1: symmetric pairs by physical column, left member first.
_PHASE1_COLUMN_PAIRS: tuple[tuple[int, int], ...] = ((4, 7), (3, 8), (2, 9), (1, 10), (5, 6))


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

    Two keys stay in one step because every consumer of the boundary treats the
    pair as a unit -- ADR-028's Phase A interleaves L-R-L-R, Phase B alternates
    four ways, the modifier branch is chosen by looking at both members, and
    ADR-012's encouragement line quotes the pair's combined coverage gain.
    """

    phase: int
    keys: tuple[KeyIntroduction, ...]


class KeyIntroducer:
    """ADR-023's two-phase introduction sequence for one profile."""

    def __init__(self, layout: Layout, source: WordSource, key_states: KeyStates) -> None:
        self._layout = layout
        self._source = source
        self._states = key_states
        # A key introduced but never answered has no key_stats row (ADR-027 §
        # First-Attempt Counting), so KeyStates cannot report it and the step
        # would repeat forever. This set is the only record that the script
        # already played, and it is deliberately session-local: see ADR-023 §
        # What the introducer remembers.
        self._introduced: set[str] = set()
        self._last_step: IntroductionStep | None = None

    def introduce_next(self) -> IntroductionStep | None:
        remaining = introduction_sequence(self._layout, self._source, self._had())
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
    layout: Layout, source: WordSource, had: AbstractSet[str] = frozenset()
) -> list[IntroductionStep]:
    """The remaining curriculum from `had`, in order. Pure: no store writes, no audio."""
    # key_stats is keyed by grapheme and this sequence by physical key, so a
    # composite the child has already typed arrives here as a name no layout
    # position exists for. Drop those rather than resolve them: a composite's
    # prerequisites are separate keys and carry their own rows.
    running = {name for name in had if name in layout.keys}
    steps: list[IntroductionStep] = []
    for slot in _phase1_slots(layout):
        pending = tuple(name for name in slot if name not in running)
        if pending:
            steps.append(_build_step(layout, 1, pending, running))
    for slot in _phase2_slots(layout, source, running):
        steps.append(_build_step(layout, 2, slot, running))
    return steps


def _phase1_slots(layout: Layout) -> list[tuple[str, ...]]:
    # Letters only. A modifier on the home row (Icelandic's dead-acute at col
    # 11) is not a location-anchoring exercise and has nothing to attach to
    # this early; it enters Phase 2 at its composite-frequency rank instead.
    by_col = {
        key.col: name
        for name, key in layout.keys.items()
        if key.row == HOME_ROW and not _is_modifier(layout, name)
    }
    slots: list[tuple[str, ...]] = []
    paired: set[str] = set()
    for left, right in _PHASE1_COLUMN_PAIRS:
        members = tuple(by_col[col] for col in (left, right) if col in by_col)
        if members:
            slots.append(members)
            paired.update(members)
    # ADR-023's "remaining row-3 letters solo" tail, outward by column so each
    # one anchors to the key introduced immediately before it.
    slots.extend((by_col[col],) for col in sorted(by_col) if by_col[col] not in paired)
    return slots


def _phase2_slots(
    layout: Layout, source: WordSource, had: AbstractSet[str]
) -> list[tuple[str, ...]]:
    frequencies = source.key_frequencies(layout)
    pools: dict[str, list[str]] = {"L": [], "R": []}
    for name in sorted(frequencies, key=lambda n: (-frequencies[n], n)):
        if name not in had:
            pools[layout.keys[name].side].append(name)
    slots: list[tuple[str, ...]] = []
    while pools["L"] or pools["R"]:
        slots.append(tuple(pools[side].pop(0) for side in ("L", "R") if pools[side]))
    return slots


def _build_step(
    layout: Layout, phase: int, names: tuple[str, ...], running: set[str]
) -> IntroductionStep:
    introductions: list[KeyIntroduction] = []
    for name in names:
        introductions.append(_introduce(layout, name, running))
        # Added as we go, so the right-hand member of a pair may anchor to the
        # left-hand one the child has just been told about.
        running.add(name)
    return IntroductionStep(phase, tuple(introductions))


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
