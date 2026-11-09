from collections.abc import Callable, Iterable, Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from typing import Protocol

from takki import config
from takki.language import WordSource
from takki.lesson.key_state import KeyStates
from takki.persistence import RestKey
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
    letters_by_position,
)

HOME_ROW = 3
DIRECT = "direct"

# The two keys with the tactile bumps, by position: row 3, columns 4 and 7,
# `f j` on QWERTY. ADR-033 keeps "anchor" for them. Never a letter list --
# German already differs at column 6 and other layouts may differ further out.
ANCHOR_COLUMNS: tuple[int, ...] = (4, 7)

# ADR-023 § Phase 1: symmetric pairs by physical column, left member first.
# With Stage 0 gone (ADR-033), the first pair is the bump letters, which is
# ADR-033's first step under every ordering.
_PHASE1_COLUMN_PAIRS: tuple[tuple[int, int], ...] = ((4, 7), (3, 8), (2, 9), (1, 10), (5, 6))


def home_anchor_keys(layout: Layout) -> tuple[str, ...]:
    """The two bump letters — `f` and `j` on QWERTY.

    Indexed unguarded: a layout with no letter on a bump is a broken premise
    for every ordering (ADR-032 § No Stage 0 above the orderings), so it fails
    loudly rather than open the curriculum somewhere else.
    """
    by_pos = letters_by_position(layout)
    return tuple(by_pos[(HOME_ROW, col)] for col in ANCHOR_COLUMNS)


@dataclass(frozen=True)
class RestCell:
    """A finger's current rest key (ADR-032 § The strategy takes the child's rest state).

    A finger present in `Rest` is chosen; absent, it has no current rest key.
    """

    row: int
    col: int
    ready: bool


# Finger id (`COL_TO_FINGER`'s) → that finger's current rest key.
Rest = Mapping[str, RestCell]


def current_rest(keys: Iterable[RestKey]) -> dict[str, RestCell]:
    """`rest_keys` rows as the order reads them: current keys only, `passed_at` ignored."""
    return {
        key.finger: RestCell(key.row, key.col, key.ready_at is not None)
        for key in keys
        if key.replaced_at is None
    }


@dataclass(frozen=True)
class Location:
    """Where a key sits relative to its finger's rest key (ADR-023, amended 2026-11-09)."""

    row_delta: int  # negative = towards the number row
    col_delta: int  # negative = towards the left edge

    @property
    def at_rest(self) -> bool:
        # The key is the finger's rest key: there is no reach to describe.
        return self.row_delta == 0 and self.col_delta == 0


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
    # From the modifier's own finger's rest key; None when that finger has none.
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
    # From the finger's rest key. None when the finger has no current rest key,
    # and for every composite, whose script names its base letter outright and
    # spends its location clause on the modifier instead.
    location: Location | None
    modifier: ModifierIntroduction | None

    @property
    def is_composite(self) -> bool:
        return self.mechanism != DIRECT


@dataclass(frozen=True)
class IntroductionStep:
    """One introduction step: one or two graphemes, left-hand member first.

    Two graphemes stay in one step because every consumer of the boundary
    treats the pair as a unit -- ADR-028's Phase A interleaves L-R-L-R, Phase B
    alternates four ways, the composite branch is chosen by looking at both
    members, and ADR-012's encouragement line quotes the pair's combined
    coverage gain.
    """

    keys: tuple[KeyIntroduction, ...]


@dataclass(frozen=True)
class IntroductionSlot:
    """One step's worth of grapheme names, before the keys are worked out."""

    keys: tuple[str, ...]


class IntroductionStrategy(Protocol):
    """The introduction order (ADR-032 § Decision 2 restated).

    Returns the slots it can see now, in order, as grapheme names, left-hand
    member first, and nothing already in `had`. `had` always holds the bump
    letters: `introduction_sequence` puts them first, above every strategy
    (rest rule 1). Filtering is the strategy's job because pairing happens
    inside it: a step thinned afterwards would be mispaired.

    Rules that bind every ordering. A composite is ineligible until its base
    letter is in `had` (`eligible`), and pools by the hand of its base stroke
    (ADR-032 § Decision 1). A letter is passed over unless `may_introduce`
    holds (rest rules 2 and 3). Letters passed over are left out, so a short
    or empty result does not mean the curriculum is finished.
    """

    def __call__(
        self, layout: Layout, source: WordSource, had: AbstractSet[str], rest: Rest
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


def may_introduce(layout: Layout, name: str, had: AbstractSet[str], rest: Rest) -> bool:
    """Rest rules 2 and 3 (ADR-032 § The strategy takes the child's rest state).

    A key on its finger's rest key needs the finger chosen; any other key needs
    it ready, because it is described and reached from the rest key. A
    composite is checked on its base stroke and, when it brings in its
    modifier, on the modifier too: the step locates the modifier from that
    finger's rest key ("What a composite would need", decided 2026-11-09).
    """
    grapheme = layout.graphemes[name]
    if not _finger_takes(base_key(layout, name), rest):
        return False
    if grapheme.mechanism == DIRECT:
        return True
    modifier = next(key for key in grapheme.prereq_keys if key != grapheme.base)
    return modifier in _keys_behind(layout, had) or _finger_takes(layout.keys[modifier], rest)


def _finger_takes(key: PhysicalKey, rest: Rest) -> bool:
    cell = rest.get(key.finger)
    if cell is None:
        return False
    return cell.ready or (cell.row, cell.col) == (key.row, key.col)


def bumps_ready(rest: Rest) -> bool:
    """Rest rule 1's gate: nothing is introduced until both index fingers are ready."""
    return all((cell := rest.get(finger)) is not None and cell.ready for finger in (L_IDX, R_IDX))


def home_row_fill(
    layout: Layout, source: WordSource, had: AbstractSet[str], rest: Rest
) -> list[IntroductionSlot]:
    """Ordering A (ADR-032 § Ordering A, formerly ADR-023 §§ Phase 1-2): the
    home row by symmetric pairs, then frequency leader per hand.

    Selectable, and the control arm if the pilot compares orders (ADR-032 §
    What Alpha ships, restated). Its steps are pairs by column, so a member
    passed over leaves its partner alone in the step, and comes back as a step
    of its own once its finger can take it.
    """
    slots = phase1_slots(layout, had, rest)
    # Every home-row letter, not only the slots: one passed over in Phase 1
    # waits for Phase 1 and must not turn up in Phase 2's pools as well.
    home = {name for (row, _), name in letters_by_position(layout).items() if row == HOME_ROW}
    slots.extend(phase2_slots(layout, source, set(had) | home, rest))
    return slots


def per_hand_alternation(
    layout: Layout, source: WordSource, had: AbstractSet[str], rest: Rest
) -> list[IntroductionSlot]:
    """Ordering C (ADR-032 § Ordering C, restated; ADR-033's order). The default.

    Each hand takes a strong rest letter when it has had more useful letters
    than strong rest letters, and otherwise its most useful letter, so its
    first turn is useful. The bump letters are in neither queue and neither
    count. A count needs only `had` and the current rest keys, so nothing is
    stored; where one kind could not be taken for a while, the other gets
    several turns in a row until it evens out, which was accepted with the rule.
    """
    bumps = set(home_anchor_keys(layout))
    by_pos = letters_by_position(layout)
    shares = source.key_shares(layout)
    ranking = source.letter_ranking(layout)
    rank = {name: index for index, name in enumerate(ranking)}
    rest_letters = {by_pos[cell] for c in rest.values() if (cell := (c.row, c.col)) in by_pos}
    strong = {
        name
        for name in rest_letters - bumps
        if shares.get(name, 0.0) >= config.REST_LETTER_MIN_SHARE
    }
    running = {name for name in had if name in layout.graphemes} | bumps
    queues: dict[bool, dict[str, list[str]]] = {
        True: {"L": [], "R": []},
        False: {"L": [], "R": []},
    }
    counts: dict[bool, dict[str, int]] = {True: {"L": 0, "R": 0}, False: {"L": 0, "R": 0}}
    for name in ranking:
        side = base_key(layout, name).side
        if name in bumps:
            continue
        if name in running:
            counts[name in strong][side] += 1
        else:
            queues[name in strong][side].append(name)
    for pool in queues[True].values():
        # Strongest first; equal shares in ranking order, never set order.
        pool.sort(key=lambda name: (-shares.get(name, 0.0), rank[name]))
    slots: list[IntroductionSlot] = []
    while True:
        step: list[str] = []
        for side in ("L", "R"):
            turn = counts[False][side] > counts[True][side]
            for kind in (turn, not turn):
                name = _take_eligible(layout, queues[kind][side], running, rest)
                if name is not None:
                    counts[kind][side] += 1
                    step.append(name)
                    break
        if not step:
            break
        running.update(step)
        slots.append(IntroductionSlot(tuple(step)))
    _refuse_baseless_composites(
        layout, [name for kind in queues.values() for pool in kind.values() for name in pool]
    )
    return slots


DEFAULT_STRATEGY: IntroductionStrategy = per_hand_alternation


class KeyIntroducer:
    """The introduction sequence for one profile, in its strategy's order."""

    def __init__(
        self,
        layout: Layout,
        source: WordSource,
        key_states: KeyStates,
        rest: Callable[[], Rest],
        strategy: IntroductionStrategy = DEFAULT_STRATEGY,
    ) -> None:
        self._layout = layout
        self._source = source
        self._states = key_states
        # Read each time the order is worked out, as `had` is, not once here:
        # the alignment opens the session and marks fingers ready, and an
        # order read before it would be yesterday's (ADR-032 § The strategy
        # takes the child's rest state).
        self._rest = rest
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

    def upcoming(self) -> IntroductionStep | None:
        """The step `introduce_next` would emit, without emitting it."""
        remaining = introduction_sequence(
            self._layout, self._source, self._had(), self._rest(), self._strategy
        )
        # The order is a forecast: None means nothing may be introduced now,
        # not that the curriculum is finished.
        return remaining[0] if remaining else None

    def introduce_next(self) -> IntroductionStep | None:
        step = self.upcoming()
        if step is None:
            return None
        self._introduced.update(k.grapheme for k in step.keys)
        self._last_step = step
        return step

    @property
    def last_step(self) -> IntroductionStep | None:
        # ADR-023: the child can re-hear the introduction script via the re-read key.
        return self._last_step

    def remember(self, step: IntroductionStep) -> None:
        """Adopt a step this introducer did not emit — a resumed one.

        Without this, a session that resumes a ramp-up (alpha-plan #12d) never
        emits a step, so `last_step` stays None and the re-read key has nothing
        to say: a blind child presses it between blocks and hears silence.
        """
        self._introduced.update(k.grapheme for k in step.keys)
        self._last_step = step

    def _had(self) -> set[str]:
        return self._states.active_keys() | self._introduced


def introduction_sequence(
    layout: Layout,
    source: WordSource,
    had: AbstractSet[str],
    rest: Rest,
    strategy: IntroductionStrategy = DEFAULT_STRATEGY,
) -> list[IntroductionStep]:
    """The steps that may come from `had` and `rest`, in order. Pure: no store writes, no audio.

    Rest rule 1 is applied here, once, above every strategy: nothing until both
    index fingers are ready, then the bump letters first, together.
    """
    # `had` is grapheme names throughout -- key_stats is keyed by grapheme
    # (ADR-011) and so is the introducer's own record. Anything the layout does
    # not produce is dropped rather than resolved.
    introduced = {name for name in had if name in layout.graphemes}
    if not bumps_ready(rest):
        return []
    bumps = home_anchor_keys(layout)
    slots = (
        [IntroductionSlot(pending)]
        if (pending := tuple(b for b in bumps if b not in introduced))
        else []
    )
    slots.extend(strategy(layout, source, introduced | set(bumps), rest))
    # The second, separate running set: the physical keys the child can strike.
    # It is not the first one with the composites removed -- a composite adds
    # its modifier here without ever being a key itself, and that modifier is
    # exactly what must not be re-announced later. The two sets answer
    # different questions (what has been taught, what can be pointed at) and
    # come apart the moment a language has a composite in it. Since the
    # location rule moved to the rest key (2026-11-09), `struck` answers only
    # whether a modifier is new; the location reads `rest`.
    struck = _keys_behind(layout, introduced)
    return [_build_step(layout, slot, introduced, struck, rest) for slot in slots]


def _keys_behind(layout: Layout, graphemes: AbstractSet[str]) -> set[str]:
    return {key for name in graphemes for key in layout.graphemes[name].prereq_keys}


def phase1_slots(layout: Layout, had: AbstractSet[str], rest: Rest) -> list[IntroductionSlot]:
    """Ordering A's Phase 1. Public because it is this ordering's own structure
    and is asserted as such; nothing outside `home_row_fill` composes it."""
    # Letters only, and by position, so this phase never sees a composite: a
    # composite has no column of its own. A modifier on the home row
    # (Icelandic's dead-acute at col 11) is not a location-anchoring exercise
    # and produces nothing the child can hear, so its column is treated as a
    # column with no letter and the partner is introduced solo.
    by_col = {
        col: name for (row, col), name in letters_by_position(layout).items() if row == HOME_ROW
    }
    slots: list[IntroductionSlot] = []
    paired: set[str] = set()
    for left, right in _PHASE1_COLUMN_PAIRS:
        members = tuple(by_col[col] for col in (left, right) if col in by_col)
        paired.update(members)
        pending = tuple(
            name for name in members if name not in had and may_introduce(layout, name, had, rest)
        )
        if pending:
            slots.append(IntroductionSlot(pending))
    # ADR-023's "remaining row-3 letters solo" tail, outward by column so each
    # one anchors to the key introduced immediately before it.
    tail = (by_col[col] for col in sorted(by_col) if by_col[col] not in paired)
    slots.extend(
        IntroductionSlot((name,))
        for name in tail
        if name not in had and may_introduce(layout, name, had, rest)
    )
    return slots


def phase2_slots(
    layout: Layout, source: WordSource, had: AbstractSet[str], rest: Rest
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
            name
            for side in ("L", "R")
            if (name := _take_eligible(layout, pools[side], running, rest))
        )
        if not leaders:
            # The rest wait on fingers not ready, on a base not yet had, or
            # can never come: only the last is an error.
            _refuse_baseless_composites(layout, pools["L"] + pools["R"])
            break
        running.update(leaders)
        slots.append(IntroductionSlot(leaders))
    return slots


def _refuse_baseless_composites(layout: Layout, waiting: Iterable[str]) -> None:
    # A composite whose base letter is not itself a grapheme of this layout can
    # never be introduced: the eligibility gate can never open. ADR-032 §
    # Decision 1 rule 1 assumes a composite's base *is* a letter the child is
    # taught; a layout that breaks the assumption is a broken premise, and
    # fails loudly: silently dropping letters from a curriculum is the failure
    # nobody notices. Everything else left waiting waits on a finger.
    stuck = sorted(
        name
        for name in waiting
        if (base := layout.graphemes[name].base) is not None and base not in layout.graphemes
    )
    if stuck:
        raise ValueError(f"composites whose base letter is not a grapheme of this layout: {stuck}")


def _take_eligible(
    layout: Layout, pool: list[str], had: AbstractSet[str], rest: Rest
) -> str | None:
    # Skip past a leader that may not come yet rather than stall the pool on
    # it: a composite that outranks its own base, or a letter on a finger not
    # ready, keeps its place in the ranking, and everything behind it advances.
    for index, name in enumerate(pool):
        if eligible(layout, name, had) and may_introduce(layout, name, had, rest):
            return pool.pop(index)
    return None


def _build_step(
    layout: Layout, slot: IntroductionSlot, introduced: set[str], struck: set[str], rest: Rest
) -> IntroductionStep:
    introductions: list[KeyIntroduction] = []
    for name in slot.keys:
        introductions.append(_introduce(layout, name, introduced, struck, rest))
        # Added as we go: a pair's second member is a composite whose modifier
        # the first one brought in, and must not announce it again.
        introduced.add(name)
        struck.update(layout.graphemes[name].prereq_keys)
    return IntroductionStep(tuple(introductions))


def resume_step(
    layout: Layout, graphemes: Sequence[str], had: AbstractSet[str], rest: Rest
) -> IntroductionStep:
    """Rebuild a step already introduced (ADR-024's cross-session resume).

    The modifier clauses are as first emitted; the locations are from today's
    rest keys, so a finger that moved is not sent from where it no longer rests.
    """
    # `had` is what the child had before the step: the modifier clauses are
    # derived from it. The step's own members are taken out, so a caller
    # handing over everything introduced still hears the modifier announced.
    members = tuple(name for name in graphemes if name in layout.graphemes)
    introduced = {name for name in had if name in layout.graphemes} - set(members)
    struck = _keys_behind(layout, introduced)
    return _build_step(layout, IntroductionSlot(members), introduced, struck, rest)


def _introduce(
    layout: Layout, name: str, introduced: AbstractSet[str], struck: AbstractSet[str], rest: Rest
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
        location=None if composite else _locate(key, rest),
        modifier=_introduce_modifier(layout, grapheme, introduced, struck, rest)
        if composite
        else None,
    )


def _introduce_modifier(
    layout: Layout,
    grapheme: Grapheme,
    introduced: AbstractSet[str],
    struck: AbstractSet[str],
    rest: Rest,
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
        location=_locate(key, rest),
        # The mechanism is explained once per class, not once per key: a layout
        # with two dead keys teaches two keys but one idea.
        mechanism=None
        if _mechanism_taught(layout, grapheme.mechanism, introduced)
        else grapheme.mechanism,
    )


def _mechanism_taught(layout: Layout, mechanism: str, introduced: AbstractSet[str]) -> bool:
    return any(layout.graphemes[name].mechanism == mechanism for name in introduced)


def _locate(key: PhysicalKey, rest: Rest) -> Location | None:
    # From the finger's rest key, whether or not it carries a letter (ADR-033),
    # never from a letter the child has: the finger moves from where it rests.
    cell = rest.get(key.finger)
    if cell is None:
        return None
    return Location(key.row - cell.row, key.col - cell.col)


def key_distance(key: PhysicalKey, other: PhysicalKey) -> tuple[int, int, str]:
    """Sort key for "closest key to `key`": the drill generator's Phase B anchor
    (alpha session 9), until ADR-024's ladder replaces Phase B (#12m session (6))."""
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

# A rest letter's script ends here, where another letter's gives its reach
# (ADR-033 § Introduction order and slots; wording decided 2026-11-09).
_BUMP_LINE = "It is the key with the bump, where that finger rests."
_REST_LINE = "It is the key where that finger rests."


def describe(introduction: KeyIntroduction) -> tuple[str, str]:
    """The script on either side of the letter, which the caller speaks as itself (ADR-023)."""
    if introduction.is_composite:
        rest = _composite_clauses(introduction)
    else:
        rest = [f"Use your {FINGER_NAMES[introduction.finger]}."]
        location = introduction.location
        if location is not None and location.at_rest:
            # The index fingers rest on the bumps and on nothing else (ADR-033).
            bump = introduction.finger in (L_IDX, R_IDX)
            rest.append(_BUMP_LINE if bump else _REST_LINE)
        elif location is not None:
            rest.append(f"Reach {describe_location(location)} from where that finger rests.")
    return "New letter:", " ".join(rest)


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
        # Its own sentence, so the finger is named rather than "that finger".
        rests = f"where your {FINGER_NAMES[modifier.finger]} rests"
        place = (
            rests
            if modifier.location.at_rest
            else f"{describe_location(modifier.location)} from {rests}"
        )
        clauses.append(f"{name[0].upper()}{name[1:]} is {place}.")
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
    return " and ".join(moves)


def _spoken(char: str) -> str:
    # German ß upper-cases to "SS", which would be read out as two letters.
    upper = char.upper()
    return upper if len(upper) == 1 else char


def _count(delta: int, noun: str) -> str:
    size = abs(delta)
    word = _NUMBER_WORDS[size] if size < len(_NUMBER_WORDS) else str(size)
    return f"{word} {noun}" if size == 1 else f"{word} {noun}s"
