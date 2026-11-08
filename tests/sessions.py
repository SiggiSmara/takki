"""Sessions for tests that write attempts: an attempt's practice day is its session's (ADR-011)."""

import weakref
from datetime import date, datetime
from typing import Any

from takki.persistence import Store

_made: "weakref.WeakKeyDictionary[Any, dict[tuple[int, date | None], int]]" = (
    weakref.WeakKeyDictionary()
)


def session_for(store: Store, profile_id: int, stamp: str | None = None) -> int:
    """The profile's session for the local day of `stamp`, started at `stamp` the first time.

    So attempts dated on two local days fall in two sessions, two practice
    days, as dated attempts made two days before the practice-day number.
    No stamp is one session, started now.
    """
    day = None if stamp is None else datetime.fromisoformat(stamp).astimezone().date()
    made = _made.setdefault(store, {})
    if (profile_id, day) not in made:
        made[(profile_id, day)] = store.start_session(profile_id, stamp)
    return made[(profile_id, day)]
