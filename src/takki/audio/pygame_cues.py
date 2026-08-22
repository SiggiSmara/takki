import pygame

from takki import config
from takki.audio.cues import CueName
from takki.audio.tone import generate_sweep, generate_tone

# Cue -> class -> reserved channel (ADR-012 Sound cue channel policy). A cue
# class is never split across two constants so a future third class (the
# acknowledgement click, roadmap C15) only adds map entries.
CUE_CLASS: dict[CueName, str] = {
    "correct": "keypress",
    "error": "keypress",
    "boundary": "keypress",
    "chirp_on": "ptt",
    "chirp_off": "ptt",
}

CLASS_CHANNEL: dict[str, int] = {
    "keypress": 0,
    "ptt": 1,
}


class PygameMixerCues:
    def __init__(self) -> None:
        pygame.mixer.init(
            frequency=config.MIXER_FREQUENCY,
            size=config.MIXER_SIZE,
            channels=config.MIXER_CHANNELS,
            buffer=config.MIXER_BUFFER,
        )
        pygame.mixer.set_reserved(len(CLASS_CHANNEL))
        self._channels = {
            cue_class: pygame.mixer.Channel(index) for cue_class, index in CLASS_CHANNEL.items()
        }
        self._sounds: dict[CueName, pygame.mixer.Sound] = {
            "correct": pygame.mixer.Sound(buffer=generate_tone(**config.TONE_CORRECT)),
            "error": pygame.mixer.Sound(buffer=generate_tone(**config.TONE_ERROR)),
            "boundary": pygame.mixer.Sound(buffer=generate_tone(**config.TONE_BOUNDARY)),
            "chirp_on": pygame.mixer.Sound(buffer=generate_sweep(**config.TONE_CHIRP_ON)),
            "chirp_off": pygame.mixer.Sound(buffer=generate_sweep(**config.TONE_CHIRP_OFF)),
        }

    def play(self, cue: CueName) -> None:
        # Channel.play() always replaces whatever that channel is currently
        # playing -- this alone gives "monophonic within a class, newest wins".
        channel = self._channels[CUE_CLASS[cue]]
        channel.play(self._sounds[cue])
