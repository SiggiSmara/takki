from typing import Protocol


class DeadKeys(Protocol):
    def disarm_dead_key(self) -> None:
        """Clear a dead key's armed composition in Takki's window; main thread only (ADR-033)."""
        ...
