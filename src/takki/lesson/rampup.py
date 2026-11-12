"""ADR-024 § The ramp-up restated — the ladder's rules, and where a step's place on it is recorded.

Two halves. The functions are pure: given one letter's presses at a level they
say whether its rule, or the one bar, has been met, and how many more presses
that needs at best. `StepLadder` is the durable half: it reads and writes the
level runs (`ramp_up_levels`) and the bar (`introductions.stable_at`), because
neither can be re-derived from `key_attempts`, a window built to forget
(ADR-011).

**Where each level's evidence starts.** A level run records the letter's
lifetime press count when the step reached it: `reach_presses` rows at Reach,
`key_stats.attempt_count` at Choose and Travel. Only presses after it are read,
so a press made before the step got there counts for nothing at that level,
and no window can move the boundary.

**Reach starts again in a new session; Choose and Travel do not.** A step that
has not reached Choose is begun again from nothing after a restart, for every
member, also one that had already met Reach's rule (ADR-024, "Two kinds of
press"). So a Reach run is read only when it was begun in this session. From
Choose on, a level reached and a rule met are events that survive a restart.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from takki import config
from takki.lesson.key_state import key_speed
from takki.persistence import Attempt, KeyStat, Level, LevelRecord, ReachPress, Store

LEVELS: tuple[Level, ...] = ("reach", "choose", "travel")

# The most counted presses any reading needs: the bar's thirty. Bounding the
# read keeps a keypress from pulling a whole window back out of SQLite.
EVIDENCE_ROWS = max(config.LEVEL_UP_WINDOW, config.STABLE_ATTEMPTS)


def level_rule_met(firsts: Sequence[bool]) -> bool:
    """Reach's and Choose's rule: enough of the latest presses right at the first press."""
    return sum(firsts[-config.LEVEL_UP_WINDOW :]) >= config.LEVEL_UP_CORRECT


def level_owed(firsts: Sequence[bool]) -> int:
    """Right presses still needed for the level's rule, at best. Never zero, for block sizing."""
    for extra in range(config.LEVEL_UP_WINDOW + 1):
        if level_rule_met([*firsts, *([True] * extra)]):
            return max(1, extra)
    return config.LEVEL_UP_WINDOW


def bar_met(evidence: Sequence[Attempt], baseline: float | None = None) -> bool:
    """ADR-024's one bar, over the latest listened presses."""
    recent = evidence[-config.STABLE_ATTEMPTS :]
    if len(recent) < config.STABLE_ATTEMPTS:
        return False
    if sum(row.correct for row in recent) / len(recent) < config.STABLE_MIN_ACCURACY:
        return False
    # Speed, read the way Known reads it and against the same baseline
    # (ADR-027 § Known has a speed term). No baseline, no term: the generator
    # hands the bump letters none in their own step, and a stretch with too
    # few timed answers is the same.
    observed = key_speed(recent)
    if baseline is None or observed is None:
        return True
    return observed <= baseline * config.STABLE_MAX_LATENCY_RATIO


def bar_owed(evidence: Sequence[Attempt]) -> int:
    """Listened presses the bar still wants, for block sizing.

    A child below it once thirty are in is owed another thirty, so that blocks
    do not shrink for the child who needs the most practice (ADR-024).
    """
    owed = config.STABLE_ATTEMPTS - len(evidence)
    return owed if owed > 0 else config.STABLE_ATTEMPTS


@dataclass(frozen=True)
class MemberState:
    """One member's place on the ladder, as last read."""

    grapheme: str
    # Whether the letter has a Reach level at all (ADR-024: a rest letter and
    # the bump letters do not).
    reach: bool
    # At Reach, this run's first-press results; from Choose on, the listened
    # presses since the step reached Choose (capped at EVIDENCE_ROWS).
    firsts: tuple[bool, ...]
    evidence: tuple[Attempt, ...]
    # Met the rule of the step's level: Reach's or Choose's, or the bar at Travel.
    met: bool
    stable: bool
    # Listened presses since the step reached Travel; 0 before it.
    at_travel: int = 0


class StepLadder:
    """Reads and records one step's place on the ladder (ADR-024, ADR-011).

    The one place that decides what level a step is at. It writes, which the
    drill generator deliberately does not: a level reached and a rule met are
    durable facts about the child, in the same tier as an attempt row.
    """

    def __init__(
        self,
        store: Store,
        profile_id: int,
        session_id: int,
        members: Sequence[tuple[str, bool]],
    ) -> None:
        self._store = store
        self._profile_id = profile_id
        self._session_id = session_id
        # (grapheme, takes Reach), left-hand member first.
        self._members = tuple(members)
        self.level: Level | None = None
        self.states: dict[str, MemberState] = {}
        # What one refresh has read, so that a keypress reads each table once
        # (#12m session (6)'s review). Forgotten at the start of every refresh
        # and after every write this class makes; nothing else writes these
        # records between two of its reads, on the one connection Takki has.
        self._forget()

    def _forget(self) -> None:
        self._levels: dict[str, list[LevelRecord]] = {}
        self._presses: dict[str, list[ReachPress]] = {}
        self._stats: dict[str, KeyStat] | None = None
        self._stable_set: set[str] | None = None

    @property
    def graphemes(self) -> tuple[str, ...]:
        return tuple(grapheme for grapheme, _ in self._members)

    def takes_reach(self, grapheme: str) -> bool:
        return dict(self._members)[grapheme]

    def refresh(self, baseline: Callable[[str], float | None]) -> None:
        """Record every event the latest press brought, climb as far as it goes, and read the step.

        `level` is None once every member has met the bar: the ramp-up has
        ended. A climb that a later level's evidence already satisfies goes on
        in the same call, so the bar is read the moment the step is at Travel.
        """
        self._forget()
        while True:
            level = self._level()
            if level is None:
                self.level = None
                self.states = {}
                return
            self._begin_missing(level)
            self.states = {
                grapheme: self._read(grapheme, reach, level) for grapheme, reach in self._members
            }
            self.level = level
            if not self._record(level, baseline):
                return

    # ---- reading --------------------------------------------------------

    def _records(self, grapheme: str) -> list[LevelRecord]:
        if grapheme not in self._levels:
            self._levels[grapheme] = self._store.level_records(self._profile_id, grapheme)
        return self._levels[grapheme]

    def _reach_presses(self, grapheme: str) -> list[ReachPress]:
        if grapheme not in self._presses:
            self._presses[grapheme] = self._store.reach_presses(self._profile_id, grapheme)
        return self._presses[grapheme]

    def _run(self, grapheme: str, level: Level) -> LevelRecord | None:
        runs = [record for record in self._records(grapheme) if record.level == level]
        if level == "reach":
            runs = [record for record in runs if record.session_id == self._session_id]
        return runs[0] if runs else None

    def _stable(self) -> set[str]:
        if self._stable_set is None:
            self._stable_set = {
                entry.key_char
                for entry in self._store.introductions(self._profile_id)
                if entry.stable_at is not None
            }
        return self._stable_set

    def _level(self) -> Level | None:
        if set(self.graphemes) <= self._stable():
            return None
        # The highest level any member has begun. The step climbs together, so
        # members differ only when a session ended between two writes; the
        # missing begins are written by `_begin_missing`.
        begun = {record.level for grapheme in self.graphemes for record in self._records(grapheme)}
        if "travel" in begun:
            return "travel"
        if "choose" in begun or not any(reach for _, reach in self._members):
            return "choose"
        return "reach"

    def _attempts(self, grapheme: str) -> int:
        if self._stats is None:
            self._stats = self._store.key_stats(self._profile_id)
        stat = self._stats.get(grapheme)
        return stat.attempt_count if stat is not None else 0

    def _reach_count(self, grapheme: str) -> int:
        return len(self._reach_presses(grapheme))

    def _begin_missing(self, level: Level) -> None:
        for grapheme, reach in self._members:
            if level == "reach" and not reach:
                # Not prompted until the step reaches Choose (ADR-024, "Pairs").
                continue
            if self._run(grapheme, level) is not None:
                continue
            presses = self._reach_count(grapheme) if level == "reach" else self._attempts(grapheme)
            self._store.begin_level(self._profile_id, grapheme, level, self._session_id, presses)
            self._forget()

    def _read(self, grapheme: str, reach: bool, level: Level) -> MemberState:
        stable = grapheme in self._stable()
        if level == "reach":
            if not reach:
                return MemberState(grapheme, reach, (), (), True, stable)
            run = self._run(grapheme, "reach")
            assert run is not None
            presses = self._reach_presses(grapheme)
            firsts = tuple(press.correct for press in presses[run.started_presses :])
            met = run.completed_presses is not None or level_rule_met(firsts)
            return MemberState(grapheme, reach, firsts, (), met, stable)
        choose = self._run(grapheme, "choose")
        assert choose is not None
        since = self._attempts(grapheme) - choose.started_presses
        evidence: tuple[Attempt, ...] = ()
        if since > 0:
            # Evidence starts where the step reached Choose, counted in lifetime
            # attempts so that an evicted row cannot move the boundary.
            evidence = tuple(
                self._store.window_attempts(
                    self._profile_id, grapheme, limit=min(since, EVIDENCE_ROWS)
                )
            )
        firsts = tuple(row.correct for row in evidence)
        if level == "choose":
            met = choose.completed_presses is not None or level_rule_met(firsts)
            return MemberState(grapheme, reach, firsts, evidence, met, stable)
        travel = self._run(grapheme, "travel")
        assert travel is not None
        at_travel = self._attempts(grapheme) - travel.started_presses
        return MemberState(grapheme, reach, firsts, evidence, stable, stable, at_travel)

    # ---- recording ------------------------------------------------------

    def _record(self, level: Level, baseline: Callable[[str], float | None]) -> bool:
        """Write the events now met at `level`. True when the step climbed."""
        if level == "travel":
            for grapheme, state in self.states.items():
                # Travel gets presses of its own before the bar is read, so a
                # member that was ahead of its partner at Choose, with thirty
                # good presses already, still meets the hand arriving from
                # elsewhere (decided by the developer, #12m session (6)).
                if (
                    not state.stable
                    and state.at_travel >= config.LEVEL_UP_CORRECT
                    and bar_met(state.evidence, baseline(grapheme))
                ):
                    self._store.record_stable(self._profile_id, grapheme, self._attempts(grapheme))
                    self._forget()
            return set(self.graphemes) <= self._stable()
        for grapheme, state in self.states.items():
            if level == "reach" and not state.reach:
                continue
            run = self._run(grapheme, level)
            assert run is not None
            if state.met and run.completed_presses is None:
                presses = (
                    self._reach_count(grapheme) if level == "reach" else self._attempts(grapheme)
                )
                self._store.complete_level(
                    self._profile_id, grapheme, level, run.session_id, presses
                )
                self._forget()
        if not all(state.met for state in self.states.values()):
            return False
        following = LEVELS[LEVELS.index(level) + 1]
        self._begin_missing(following)
        return True

    # ---- block sizing ----------------------------------------------------

    def owed(self, grapheme: str) -> int:
        """Presses this member still owes the step's level, at best; 0 when it owes none."""
        state = self.states.get(grapheme)
        if state is None or self.level is None or state.met:
            return 0
        if self.level == "travel":
            at_travel = config.LEVEL_UP_CORRECT - state.at_travel
            # Optimistic, as all sizing is: speed is not read here.
            if bar_met(state.evidence):
                return max(1, at_travel)
            return max(bar_owed(state.evidence), at_travel)
        return level_owed(state.firsts)
