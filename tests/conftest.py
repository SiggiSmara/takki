import os

# Headless SDL: no display, no real audio device, for the whole suite
# (matches CI's job-level env in .github/workflows/ci.yml).
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
