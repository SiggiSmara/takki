"""Compiled configuration defaults (ADR-025). Overridable by takki_config.yaml
and per-profile SQLite settings once those tiers land -- Alpha reads these
values directly."""

# Key bindings (ADR-025). Values are pynput key *name* strings -- what
# Key.<member>.name returns, which is what session 5's translate() puts in
# KeyEvent.name. ADR-025's listing writes REREAD/RESTART as "escape"; pynput
# has no such member, so the binding that actually matches is "esc".
TALK_KEY = "ctrl_r"
REREAD_KEY = "esc"
RESTART_KEY = "esc"  # held; a tap on the same key re-reads -- ADR-012 § Recovery
RESTART_HOLD_MS = 800  # separates restart from re-read; unused when the two keys differ

# Resume-from-PAUSED held key (ADR-028 § C8 "Resume hold"). Not in ADR-025's
# binding list -- proposed here as an amendment, see the session 6b report.
# This key is held while *another* app has focus, so the binding must be one
# nobody holds for a second by accident. That rules out the bare modifiers:
# Ctrl (Ctrl+click, Ctrl+scroll, Ctrl+Shift+arrow) and Shift (Shift+arrow
# selection) are held past a second constantly, and Right Shift held 8 s also
# trips Windows FilterKeys. F1 is held by nobody, needs no chord, and is found
# by edge and by its neighbour Escape -- no counting and no reliance on F-group
# gaps, which laptops and dense keyboards do not have. Its one side effect,
# opening the foreground app's help, costs a window Takki is about to raise
# past anyway. The Escape adjacency cuts the right way: the two keys are live
# in opposite states, so a child groping for Escape while PAUSED lands on the
# key that brings them back.
RESUME_KEY = "f1"
# Longer than RESTART_HOLD_MS: this gesture fires while another app holds focus,
# where an accidental trigger yanks the user out of what they were doing.
RESUME_HOLD_MS = 1000
# How long a request_foreground() gets to produce a FocusGained before Takki
# speaks the Alt+Tab fallback. The request has no synchronous answer (ADR-028
# § Re-acquire), so expiry is the only failure signal there is.
RESUME_REQUEST_TIMEOUT_MS = 1500

# Sound cue asset paths (relative to bundle assets/sounds/). Alpha has no
# bundled assets and no takki_config.yaml override chain -- these paths are
# inert until the Beta config loader resolves them (ADR-012).
SOUND_CORRECT = "correct.wav"
SOUND_ERROR = "error.wav"
SOUND_BOUNDARY = "boundary.wav"
SOUND_CHIRP_ON = "chirp_on.wav"
SOUND_CHIRP_OFF = "chirp_off.wav"

# Alpha placeholder tone parameters -- generated in-process (takki.audio.tone),
# no binary assets committed to source.
TONE_CORRECT = dict(freq=880, duration_ms=200, fade_ms=30)
TONE_ERROR = dict(freq=220, duration_ms=180, fade_ms=20)
TONE_BOUNDARY = dict(freq=440, duration_ms=100, fade_ms=10)
TONE_CHIRP_ON = dict(freq_start=660, freq_end=1100, duration_ms=150)
TONE_CHIRP_OFF = dict(freq_start=1100, freq_end=660, duration_ms=150)

# pygame.mixer init, pinned rather than left to the pygame default (ADR-012):
# MIXER_BUFFER is the floor on cue latency -- 512 samples is ~23ms at 22050 Hz.
# Must not drift silently with a pygame version bump.
MIXER_FREQUENCY = 22050
MIXER_SIZE = -16  # signed 16-bit
MIXER_CHANNELS = 2  # stereo
MIXER_BUFFER = 512

# Always-on focus-owning window (ADR-016/ADR-028). Blank in audio-only mode --
# size is irrelevant to the child, who navigates by audio; the title is what a
# screen reader announces on Alt+Tab.
WINDOW_WIDTH = 640
WINDOW_HEIGHT = 480
WINDOW_TITLE = "Takki"

# Key & accuracy state model (ADR-027). ATTEMPT_WINDOW is the per-(profile, key)
# rolling window the Known criterion is evaluated over; the three KNOWN_* floors
# are that criterion. These are research floors, not taste -- 200 is the window
# that cannot be filled in one sitting, 90 the graphomotor retention floor, 2 the
# minimum number of calendar days that guarantees a night of consolidation. See
# research/motor-learning-repetitions.md before moving any of them.
ATTEMPT_WINDOW = 200
KNOWN_MIN_ATTEMPTS = 90
KNOWN_MIN_ACCURACY = 0.90
KNOWN_MIN_DISTINCT_DAYS = 2

# ADR-027 § The Anchor Gate. The first milestone rung's bar for the six index
# home-column keys: shorter than the general Known floor and stricter on
# accuracy, because a child who is only 90% sure where home is has no anchor.
# The distinct-day floor is shared with Known -- consolidation is the same
# mechanism either way. Anchor accuracy is also maintained for the life of the
# profile: falling below ANCHOR_MIN_ACCURACY on f or j re-injects return-drills.
ANCHOR_MIN_ATTEMPTS = 25
ANCHOR_MIN_ACCURACY = 0.95
