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
    Grapheme,
    Layout,
    PhysicalKey,
)

HOME_ROW = 3
DIRECT = "direct"

# ADR-032 § What this changes in the engine item 3: the only two values a step
# can carry. Phase 1 and Phase 2 are Ordering A's internal structure, so they
# are not values of a field every ordering shares.
STAGE_0 = 0
CURRICULUM = 1

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
    # Indexed unguarded, unlike phase1_slots' `if col in by_col`. That guard
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
class ModifierIntroduction:
    """The modifier a composite needs, announced inside that composite's step.

    ADR-032 § Decision 1: a modifier has no rank and no step of its own. It
    rides in on the first composite that needs it, and later composites on the
    same key carry no `ModifierIntroduction` at all -- they are new letters
    made of keys the child already has.
    """

    key: str  # "dead-acute", "altgr"
    finger: str
    location: Location | None
    # The mechanism class to explain in words, or None when a composite of
    # this class has already been introduced. Two dead keys in one layout are
    # two new keys but one mechanism, so newness of the key and newness of the
    # explanation are separate questions and are answered separately.
    mechanism: str | None


@dataclass(frozen=True)
class KeyIntroduction:
    """One grapheme, and the keys it takes to produce it (ADR-032 § Decision 1).

    The name is ADR-032's own (§ What this changes in the engine item 2): what
    is introduced is the character the child produces, and the keys are pulled
    in by it.
    """

    grapheme: str
    mechanism: str  # "direct", "dead-key", "altgr-chord"
    keys: tuple[str, ...]  # every physical key, in stroke order
    base: str  # the letter key struck; the grapheme itself when direct
    # Finger and hand of the *base* stroke. ADR-032 § Decision 1 rule 2: the
    # modifier stroke is identical for every composite of a class and balances
    # nothing, so the base stroke is what pools a composite by hand.
    finger: str
    side: str
    # None for the very first grapheme introduced -- nothing anchors it yet --
    # and for every composite, whose script names its base letter outright and
    # spends its location clause on the modifier instead. Locating a composite
    # against the base it already requires would be a self-reference.
    location: Location | None
    modifier: ModifierIntroduction | None

    @property
    def is_composite(self) -> bool:
        return self.mechanism != DIRECT


@dataclass(frozen=True)
class IntroductionStep:
    """One introduction step: one or two graphemes, left-hand member first.

    `stage` is 0 for Stage 0 (ADR-023 § Stage 0 -- anchor establishment) and 1
    for the curriculum below it. It is not the ordering's phase: ADR-032 § What
    this changes in the engine item 3 -- Phase 1 and Phase 2 belong to Ordering
    A, and a field every ordering shares must not claim them.

    Two graphemes stay in one step because every consumer of the boundary
    treats the pair as a unit -- ADR-028's Phase A interleaves L-R-L-R, Phase B
    alternates four ways, the composite branch is chosen by looking at both
    members, and ADR-012's encouragement line quotes the pair's combined
    coverage gain.
    """

    stage: int
    keys: tuple[KeyIntroduction, ...]


@dataclass(frozen=True)
class IntroductionSlot:
    """One step's worth of grapheme names, before the keys are worked out."""

    stage: int
    keys: tuple[str, ...]


class IntroductionStrategy(Protocol):
    """The introduction order *below* Stage 0 (ADR-032 § Decision 2).

    Returns every remaining slot in order as grapheme names, left-hand member
    first, and returns nothing that is already in `had`. Filtering is the
    strategy's job because pairing happens after it: a strategy that ignored
    `had` would mispair the survivors, not merely repeat itself.

    Two rules bind every ordering, not just the one that ships. A composite is
    ineligible until its base letter is in `had` (`eligible` below), and a
    composite pools by the hand of its base stroke -- both ADR-032 § Decision 1.
    """

    def __call__(
        self, layout: Layout, source: WordSource, had: AbstractSet[str]
    ) -> list[IntroductionSlot]: ...


def eligible(layout: Layout, name: str, had: AbstractSet[str]) -> bool:
    """ADR-032 § Decision 1 rule 1 — no composite before its own base letter.

    Otherwise the step would teach a new finger position and a new mechanism at
    once, which is what ADR-024's ramp-up exists to prevent. A base letter
    outranks its own composites in every language measured, so this rarely
    binds; when it does, the ordering skips past the composite rather than
    stalling on it.
    """
    grapheme = layout.graphemes[name]
    return grapheme.mechanism == DIRECT or grapheme.base in had


def base_key(layout: Layout, name: str) -> PhysicalKey:
    grapheme = layout.graphemes[name]
    return layout.keys[grapheme.base or grapheme.char]


def home_row_fill(
    layout: Layout, source: WordSource, had: AbstractSet[str]
) -> list[IntroductionSlot]:
    """Ordering A (ADR-032 § Ordering A, formerly ADR-023 §§ Phase 1-2): the
    home row by symmetric pairs, then frequency leader per hand.

    The default, and the only ordering Alpha ships. The choice between it, an
    F/J-seeded order and a per-child calibrated one belongs to the Beta pilot
    (ADR-032 open questions 1 and 4, roadmap B9) -- this seam exists so that
    choice costs a constructor argument rather than an engine rewrite.
    """
    slots = phase1_slots(layout, had)
    running = set(had) | {name for slot in slots for name in slot.keys}
    slots.extend(phase2_slots(layout, source, running))
    return slots


DEFAULT_STRATEGY: IntroductionStrategy = home_row_fill


class KeyIntroducer:
    """The introduction sequence for one profile: Stage 0, then a strategy."""

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
        # A grapheme introduced but never answered has no key_stats row (ADR-027
        # § First-Attempt Counting), so KeyStates cannot report it and the step
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
        self._introduced.update(k.grapheme for k in step.keys)
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
    # `had` is grapheme names throughout -- key_stats is keyed by grapheme
    # (ADR-011) and so is the introducer's own record. Anything the layout does
    # not produce is dropped rather than resolved.
    introduced = {name for name in had if name in layout.graphemes}
    # The second, separate running set: the physical keys the child can strike.
    # It is not the first one with the composites removed -- a composite adds
    # its modifier here without ever being a key itself, and that modifier is
    # exactly what must not be re-announced later. The two sets answer
    # different questions (what has been taught, what can be pointed at) and
    # come apart the moment a language has a composite in it.
    struck = _keys_behind(layout, introduced)
    steps: list[IntroductionStep] = []
    for slot in _stage0_slots(layout, introduced):
        steps.append(_build_step(layout, slot, introduced, struck))
    # Stage 0's keys are ordinary curriculum keys as well -- f and j open the
    # default strategy's Phase 1, r v u m are Phase 2 keys -- so the strategy
    # is handed them in `had` and skips them. It is called after the loop
    # above, which is what puts them there.
    for slot in strategy(layout, source, introduced):
        steps.append(_build_step(layout, slot, introduced, struck))
    return steps


def _keys_behind(layout: Layout, graphemes: AbstractSet[str]) -> set[str]:
    return {key for name in graphemes for key in layout.graphemes[name].prereq_keys}


def _stage0_slots(layout: Layout, had: AbstractSet[str]) -> list[IntroductionSlot]:
    """ADR-023 § Stage 0 — one row of the two index columns per step.

    Each step is a symmetric pair by physical position, exactly as Phase 1
    pairs are, so nothing downstream needs a second shape for the stage: the
    left-hand member is first and ADR-028's pair ramp-up reads off the step
    unchanged. What marks the stage is `stage`, which the drill generator
    needs anyway to pick Stage 0's own content.
    """
    by_pos = {(key.row, key.col): name for name, key in layout.keys.items()}
    slots: list[IntroductionSlot] = []
    for row in ANCHOR_ROWS:
        pending = tuple(name for col in ANCHOR_COLUMNS if (name := by_pos[(row, col)]) not in had)
        if pending:
            slots.append(IntroductionSlot(STAGE_0, pending))
    return slots


def phase1_slots(layout: Layout, had: AbstractSet[str]) -> list[IntroductionSlot]:
    """Ordering A's Phase 1. Public because it is this ordering's own structure
    and is asserted as such; nothing outside `home_row_fill` composes it."""
    # Letters only, and by position, so this phase never sees a composite: a
    # composite has no column of its own. A modifier on the home row
    # (Icelandic's dead-acute at col 11) is not a location-anchoring exercise
    # and produces nothing the child can hear, so its column is treated as a
    # column with no letter and the partner is introduced solo.
    by_col = {
        key.col: name
        for name, key in layout.keys.items()
        if key.row == HOME_ROW and name in layout.graphemes
    }
    slots: list[IntroductionSlot] = []
    paired: set[str] = set()
    for left, right in _PHASE1_COLUMN_PAIRS:
        members = tuple(by_col[col] for col in (left, right) if col in by_col)
        paired.update(members)
        pending = tuple(name for name in members if name not in had)
        if pending:
            slots.append(IntroductionSlot(CURRICULUM, pending))
    # ADR-023's "remaining row-3 letters solo" tail, outward by column so each
    # one anchors to the key introduced immediately before it.
    tail = (by_col[col] for col in sorted(by_col) if by_col[col] not in paired)
    slots.extend(IntroductionSlot(CURRICULUM, (name,)) for name in tail if name not in had)
    return slots


def phase2_slots(
    layout: Layout, source: WordSource, had: AbstractSet[str]
) -> list[IntroductionSlot]:
    # Graphemes, not keys (ADR-032 § Decision 1). A composite is ranked as the
    # letter it is, and the modifier it needs has no entry here at all.
    running = set(had)
    pools: dict[str, list[str]] = {"L": [], "R": []}
    for name in source.letter_ranking(layout):
        if name not in running:
            pools[base_key(layout, name).side].append(name)
    slots: list[IntroductionSlot] = []
    while pools["L"] or pools["R"]:
        leaders = tuple(
            name for side in ("L", "R") if (name := _take_eligible(layout, pools[side], running))
        )
        if not leaders:
            # Every survivor is a composite whose base letter is not itself a
            # grapheme of this layout, so the curriculum can never introduce it
            # and the eligibility gate can never open. ADR-032 § Decision 1
            # rule 1 assumes a composite's base *is* a letter the child is
            # taught; a layout that breaks the assumption is a broken premise,
            # and fails loudly for the same reason anchor_keys does -- silently
            # dropping letters from a curriculum is the failure nobody notices.
            # Reachable only from session 12's real layout data.
            stuck = sorted(pools["L"] + pools["R"])
            raise ValueError(
                f"composites whose base letter is not a grapheme of this layout: {stuck}"
            )
        running.update(leaders)
        slots.append(IntroductionSlot(CURRICULUM, leaders))
    return slots


def _take_eligible(layout: Layout, pool: list[str], had: AbstractSet[str]) -> str | None:
    # Skip past an ineligible leader rather than stall the pool on it: a
    # composite that outranks its own base waits for the base and keeps its
    # place in the ranking, and everything behind it still advances.
    for index, name in enumerate(pool):
        if eligible(layout, name, had):
            return pool.pop(index)
    return None


def _build_step(
    layout: Layout, slot: IntroductionSlot, introduced: set[str], struck: set[str]
) -> IntroductionStep:
    introductions: list[KeyIntroduction] = []
    for name in slot.keys:
        introductions.append(_introduce(layout, name, introduced, struck))
        # Added as we go, so the right-hand member of a pair may anchor to the
        # left-hand one the child has just been told about.
        introduced.add(name)
        struck.update(layout.graphemes[name].prereq_keys)
    return IntroductionStep(slot.stage, tuple(introductions))


def _introduce(
    layout: Layout, name: str, introduced: AbstractSet[str], struck: AbstractSet[str]
) -> KeyIntroduction:
    grapheme = layout.graphemes[name]
    key = base_key(layout, name)
    composite = grapheme.mechanism != DIRECT
    return KeyIntroduction(
        grapheme=name,
        mechanism=grapheme.mechanism,
        keys=grapheme.prereq_keys,
        base=key.name,
        finger=key.finger,
        side=key.side,
        location=None if composite else _locate(layout, key, struck),
        modifier=_introduce_modifier(layout, grapheme, introduced, struck) if composite else None,
    )


def _introduce_modifier(
    layout: Layout, grapheme: Grapheme, introduced: AbstractSet[str], struck: AbstractSet[str]
) -> ModifierIntroduction | None:
    modifier = next(key for key in grapheme.prereq_keys if key != grapheme.base)
    if modifier in struck:
        # ADR-032 § Decision 1 rule 2: every later composite on this key
        # introduces no key at all. Whether the key is new is read off the keys
        # the child has struck, which is where the first composite put it --
        # not off a second record of what has been announced. The two would
        # differ only for a composite introduced and never answered, and there
        # the derived answer is the wanted one: the introduction is owed again
        # next session, modifier clause included, because the script is that
        # letter's only teaching moment (ADR-023 § What the introducer
        # remembers).
        return None
    key = layout.keys[modifier]
    return ModifierIntroduction(
        key=modifier,
        finger=key.finger,
        location=_locate(layout, key, struck),
        # The mechanism is explained once per class, not once per key: a layout
        # with two dead keys teaches two keys but one idea.
        mechanism=None
        if _mechanism_taught(layout, grapheme.mechanism, introduced)
        else grapheme.mechanism,
    )


def _mechanism_taught(layout: Layout, mechanism: str, introduced: AbstractSet[str]) -> bool:
    return any(layout.graphemes[name].mechanism == mechanism for name in introduced)


def _locate(layout: Layout, key: PhysicalKey, struck: AbstractSet[str]) -> Location | None:
    # A modifier produces no character and makes no sound of its own, so it is
    # never the anchor another key is described against -- it only receives one.
    # The key being located is excluded as well: `struck` can already hold it
    # when a composite pulled it in as a base stroke, and `min` would then
    # return a zero-distance self-reference ("reach nowhere from A").
    candidates = [
        layout.keys[name] for name in struck if name in layout.graphemes and name != key.name
    ]
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

# ADR-023 § Composite letters: the dead-key script is sequential, the
# AltGr-chord script simultaneous.
_COMPOSITE_SCRIPTS: dict[str, str] = {
    "dead-key": "Press {modifier} first, then {base}.",
    "altgr-chord": "Press {modifier} and {base} together.",
}

_NUMBER_WORDS: tuple[str, ...] = ("zero", "one", "two", "three", "four")


def describe(introduction: KeyIntroduction) -> str:
    parts = [f"New letter: {_spoken(introduction.grapheme)}."]
    if introduction.is_composite:
        parts.extend(_composite_clauses(introduction))
    else:
        parts.append(f"Use your {FINGER_NAMES[introduction.finger]}.")
        if introduction.location is not None:
            parts.append(f"Reach {describe_location(introduction.location)}.")
    return " ".join(parts)


def _composite_clauses(introduction: KeyIntroduction) -> list[str]:
    modifier_key = next(key for key in introduction.keys if key != introduction.base)
    name = MODIFIER_NAMES.get(modifier_key, modifier_key)
    script = _COMPOSITE_SCRIPTS[introduction.mechanism]
    clauses = [script.format(modifier=name, base=_spoken(introduction.base))]
    modifier = introduction.modifier
    if modifier is None:
        return clauses
    # ADR-032 § What a modifier still gets: name, location relative to a key
    # the child has, and mechanism -- all inside the composite's own step.
    if modifier.location is not None:
        clauses.append(f"{name[0].upper()}{name[1:]} is {describe_location(modifier.location)}.")
    if modifier.mechanism is not None:
        clauses.append(MECHANISM_NOTES[modifier.mechanism])
    return clauses


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
