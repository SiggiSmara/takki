"""Rest states for tests: the order reads each finger's current rest key (ADR-032 rest rules)."""

from takki.lesson.introducer import RestCell
from takki.persistence import Store
from takki.platform.layout import COL_TO_FINGER, L_IDX, R_IDX

# The conventional rest position, row 3, columns 1-4 and 7-10.
CONVENTIONAL_COLUMNS: tuple[int, ...] = (1, 2, 3, 4, 7, 8, 9, 10)

# Every finger chosen and ready on the conventional position.
READY: dict[str, RestCell] = {
    COL_TO_FINGER[col]: RestCell(3, col, True) for col in CONVENTIONAL_COLUMNS
}


def seed_rest(store: Store, profile_id: int, *, not_ready: tuple[str, ...] = ()) -> None:
    """Write the conventional rest keys, every finger ready but those named."""
    for col in CONVENTIONAL_COLUMNS:
        finger = COL_TO_FINGER[col]
        store.choose_rest_key(
            profile_id, finger, 3, col, "bump" if finger in (L_IDX, R_IDX) else "landings"
        )
        if finger not in not_ready:
            store.mark_rest_key_ready(profile_id, finger)
