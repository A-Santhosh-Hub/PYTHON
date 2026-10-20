import json

import pytest

from app import hotkeys
from app.mapping import templates
from app.mapping.profile import Binding, Profile, ProfileError, ProfileStore


# ---------------------------------------------------------------- templates
def test_standard_template_has_the_expected_controls():
    p = templates.build(templates.STANDARD, "G", "landscape", package="com.x")
    assert {b.input for b in p.bindings} >= {"LMB", "RMB", "R", "C", "Space", "Shift", "M", "WheelUp", "WheelDown"}
    assert len(p.sticks) == 1 and len(p.looks) == 1 and p.package == "com.x" and p.orientation == "landscape"
    assert p.find("LMB").mode == "hold" and p.find("M").mode == "tap"
    assert len({(b.x, b.y) for b in p.bindings}) == len(p.bindings)            # nothing stacked


def test_empty_template_is_empty():
    p = templates.build(templates.EMPTY, "G")
    assert not p.bindings and not p.sticks and not p.looks


def test_apply_template_resets_but_keeps_identity():
    p = Profile("Mine", "landscape", [Binding("Z", 0.1, 0.1)], package="com.game")
    templates.apply_template(p, templates.STANDARD)
    assert p.find("Z") is None and p.find("LMB") is not None
    assert (p.name, p.package, p.orientation) == ("Mine", "com.game", "landscape")
    templates.apply_template(p, templates.EMPTY)
    assert not p.bindings and not p.sticks and not p.looks and p.package == "com.game"


def test_template_roundtrips_through_a_file(tmp_path):
    store = ProfileStore(tmp_path)
    store.save(templates.build(templates.STANDARD, "G"))
    assert store.load("G").to_dict() == templates.build(templates.STANDARD, "G").to_dict()


# ---------------------------------------------------------------- restore points
def test_checkpoint_lifecycle(tmp_path):
    store = ProfileStore(tmp_path)
    p = templates.build(templates.STANDARD, "G")
    store.save(p)
    assert not store.has_checkpoint("G") and store.has_unsaved_changes(p) is False
    store.save_checkpoint(p)
    assert store.has_checkpoint("G") and store.has_unsaved_changes(p) is False and store.checkpoint_time("G")
    p.add(Binding("Q", 0.3, 0.3))
    store.save(p)
    assert store.has_unsaved_changes(p) is True                      # autosaved, but differs from the restore point
    restored = store.load_checkpoint("G")
    assert restored.find("Q") is None and restored.find("LMB") is not None
    store.save_checkpoint(p)
    assert store.has_unsaved_changes(p) is False


def test_checkpoint_does_not_show_up_as_a_profile_and_dies_with_it(tmp_path):
    store = ProfileStore(tmp_path)
    p = Profile("G")
    store.save(p)
    store.save_checkpoint(p)
    assert store.names() == ["G"]
    store.delete("G")
    assert store.names() == [] and not store.has_checkpoint("G")


def test_missing_checkpoint_raises_a_clear_error(tmp_path):
    with pytest.raises(ProfileError):
        ProfileStore(tmp_path).load_checkpoint("nope")


def test_corrupt_checkpoint_counts_as_unchanged(tmp_path):
    store = ProfileStore(tmp_path)
    p = Profile("G")
    store.save(p)
    store.checkpoint_path("G").parent.mkdir(exist_ok=True)
    store.checkpoint_path("G").write_text("{broken", encoding="utf-8")
    assert store.has_unsaved_changes(p) is False


# ---------------------------------------------------------------- hotkeys
class FakeSettings(dict):
    def value(self, key, default=None):
        return self.get(key, default)

    def setValue(self, key, value):
        self[key] = value


def test_default_hotkeys_are_valid_and_distinct():
    assert len(set(hotkeys.DEFAULT_HOTKEYS.values())) == len(hotkeys.DEFAULT_HOTKEYS) == 8
    for action, key in hotkeys.DEFAULT_HOTKEYS.items():
        assert hotkeys.validate({}, action, key, set()) is None


@pytest.mark.parametrize("key", ["W", "Space", "Shift", "LMB", "A", "1", "Tab"])
def test_typing_keys_cannot_be_hotkeys(key):
    assert "cannot be a hotkey" in hotkeys.validate(dict(hotkeys.DEFAULT_HOTKEYS), "capture", key, set())


def test_escape_is_reserved():
    assert "Esc" in hotkeys.validate(dict(hotkeys.DEFAULT_HOTKEYS), "capture", "Esc", set())


def test_duplicate_and_profile_clash_rejected_but_own_key_allowed():
    current = dict(hotkeys.DEFAULT_HOTKEYS)
    assert "already the hotkey" in hotkeys.validate(current, "capture", "F9", set())
    assert hotkeys.validate(current, "capture", "F8", set()) is None            # unchanged
    assert hotkeys.validate(current, "capture", "F7", set()) is None
    assert "used by a control" in hotkeys.validate(current, "capture", "F7", {"F7"})


def test_hotkeys_load_save_and_corruption_fallback():
    s = FakeSettings()
    assert hotkeys.load(s) == hotkeys.DEFAULT_HOTKEYS
    changed = {**hotkeys.DEFAULT_HOTKEYS, "capture": "F7", "mapping": "F6", "fullscreen": "F10"}
    hotkeys.save(s, changed)
    assert hotkeys.load(s) == changed
    s["hotkey_capture"] = "W"                                                    # invalid value
    assert hotkeys.load(s)["capture"] == "F8"
    s2 = FakeSettings({"hotkey_capture": "F5", "hotkey_mapping": "F5", "hotkey_fullscreen": "F5"})   # duplicates
    assert hotkeys.load(s2) == hotkeys.DEFAULT_HOTKEYS
