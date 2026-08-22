import pytest

from takki import config
from takki.input import KeyEvent
from takki.input.taxonomy import (
    Boundary,
    Character,
    Composing,
    KeyBindings,
    RecoveryKey,
    ResumeKey,
    System,
    TalkKey,
    classify,
)

DEFAULTS = KeyBindings()


def named(name: str, pressed: bool = True) -> KeyEvent:
    return KeyEvent(pressed=pressed, char=None, name=name)


def typed(char: str | None, pressed: bool = True) -> KeyEvent:
    return KeyEvent(pressed=pressed, char=char, name=None)


class TestBindingDefaults:
    def test_defaults_come_from_config(self) -> None:
        assert DEFAULTS.talk == config.TALK_KEY
        assert DEFAULTS.reread == config.REREAD_KEY
        assert DEFAULTS.restart == config.RESTART_KEY
        assert DEFAULTS.resume == config.RESUME_KEY
        assert DEFAULTS.restart_hold_ms == config.RESTART_HOLD_MS
        assert DEFAULTS.resume_hold_ms == config.RESUME_HOLD_MS
        assert DEFAULTS.resume_request_timeout_ms == config.RESUME_REQUEST_TIMEOUT_MS

    def test_reread_and_restart_share_a_key_by_default(self) -> None:
        assert DEFAULTS.reread == DEFAULTS.restart

    def test_resume_key_collides_with_no_other_binding(self) -> None:
        assert DEFAULTS.resume not in (DEFAULTS.talk, DEFAULTS.reread, DEFAULTS.restart)


class TestTaxonomy:
    def test_talk_key(self) -> None:
        assert classify(named(config.TALK_KEY), DEFAULTS, paused=False) == TalkKey()

    def test_shared_recovery_key_is_bound_to_both_actions(self) -> None:
        assert classify(named(config.REREAD_KEY), DEFAULTS, paused=False) == RecoveryKey(
            reread=True, restart=True
        )

    def test_distinct_recovery_keys_are_classified_separately(self) -> None:
        bindings = KeyBindings(reread="esc", restart="f5")
        assert classify(named("esc"), bindings, paused=False) == RecoveryKey(
            reread=True, restart=False
        )
        assert classify(named("f5"), bindings, paused=False) == RecoveryKey(
            reread=False, restart=True
        )

    def test_resume_key_only_while_paused(self) -> None:
        assert classify(named(config.RESUME_KEY), DEFAULTS, paused=True) == ResumeKey()
        assert classify(named(config.RESUME_KEY), DEFAULTS, paused=False) == System()

    def test_printable_character(self) -> None:
        assert classify(typed("a"), DEFAULTS, paused=False) == Character("a")

    def test_composed_grapheme_is_an_ordinary_character(self) -> None:
        # ADR-028: the composite arrives already translated; 'á' is as atomic as 'a'.
        assert classify(typed("á"), DEFAULTS, paused=False) == Character("á")

    def test_dead_key_arm_is_composing(self) -> None:
        assert classify(typed(None), DEFAULTS, paused=False) == Composing()

    def test_non_printable_keycode_is_composing(self) -> None:
        assert classify(typed("\x01"), DEFAULTS, paused=False) == Composing()

    @pytest.mark.parametrize("name", ["backspace", "tab", "delete", "enter"])
    def test_boundary_keys(self, name: str) -> None:
        assert classify(named(name), DEFAULTS, paused=False) == Boundary()

    @pytest.mark.parametrize("name", ["f2", "cmd", "shift_r", "up", "caps_lock"])
    def test_system_keys(self, name: str) -> None:
        assert classify(named(name), DEFAULTS, paused=False) == System()

    def test_space_is_a_system_key(self) -> None:
        # pynput reports the space bar as Key.space, and ADR-023 scopes the
        # space bar out of the curriculum entirely — so it has no lesson class.
        assert classify(named("space"), DEFAULTS, paused=False) == System()

    def test_character_classes_are_identical_while_paused(self) -> None:
        # Classification is faithful in both states; dropping lesson input while
        # PAUSED is the caller's job, not the taxonomy's.
        assert classify(typed("a"), DEFAULTS, paused=True) == Character("a")
        assert classify(named(config.REREAD_KEY), DEFAULTS, paused=True) == RecoveryKey(
            reread=True, restart=True
        )

    def test_release_classifies_the_same_as_press(self) -> None:
        for event in (named(config.REREAD_KEY), typed("a"), named("space")):
            release = KeyEvent(pressed=False, char=event.char, name=event.name)
            assert classify(release, DEFAULTS, paused=False) == classify(
                event, DEFAULTS, paused=False
            )
