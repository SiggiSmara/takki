from dataclasses import dataclass


@dataclass(frozen=True)
class Quit:
    """The window closed, or a signal asked the process to stop.

    Here rather than in the loop module so the SDL pump can emit it: only
    `PygameFocusSource` sees `pygame.QUIT`, and the loop reaches pygame through
    no other route (concurrency-model.md § The loop -- "SDL: focus gained/lost,
    QUIT").
    """
