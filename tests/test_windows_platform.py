import subprocess
import sys
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.windows_only


def test_get_system_language_returns_lowercase_primary_subtag() -> None:
    if sys.platform == "win32":
        from takki.platform.windows import WindowsPlatformInterface

        lang = WindowsPlatformInterface().get_system_language()
        assert lang == lang.lower()
        assert "-" not in lang
        assert lang != ""


def test_detect_screen_reader_returns_str_or_none() -> None:
    if sys.platform == "win32":
        from takki.platform.windows import WindowsPlatformInterface

        result = WindowsPlatformInterface().detect_screen_reader()
        assert result is None or isinstance(result, str)


def test_detect_screen_reader_survives_a_hung_tasklist() -> None:
    # tasklist's TimeoutExpired is a SubprocessError, not an OSError -- a
    # narrower except clause here would let it crash startup instead of
    # degrading to "no screen reader detected".
    if sys.platform == "win32":
        from takki.platform.windows import WindowsPlatformInterface

        with patch(
            "subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="tasklist", timeout=5)
        ):
            assert WindowsPlatformInterface().detect_screen_reader() is None
