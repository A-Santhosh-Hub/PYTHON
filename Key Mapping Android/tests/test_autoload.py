from app.device.foreground import parse_foreground_package
from app.mapping.autoload import profile_to_load, should_stop_mapping
from app.mapping.profile import Binding, Profile, ProfileStore

COD = "com.activision.callofduty.shooter"


def test_parse_foreground_package():
    line = ("  topResumedActivity=ActivityRecord{220785793 u0 com.activision.callofduty.shooter/"
            "com.tencent.tmgp.cod.CODMainActivity t3048 d0}")
    assert parse_foreground_package(line) == COD
    assert parse_foreground_package("ResumedActivity: ActivityRecord{9 u10 com.android.settings/.Settings t6}") \
        == "com.android.settings"
    assert parse_foreground_package("") == "" and parse_foreground_package("nothing useful") == ""


def test_package_roundtrips_and_defaults_empty(tmp_path):
    store = ProfileStore(tmp_path)
    p = Profile("COD", package=COD, bindings=[Binding("R", 0.7, 0.8)])
    store.save(p)
    assert store.load("COD").package == COD
    assert Profile.from_dict({"name": "old", "bindings": []}).package == ""


def test_find_by_package(tmp_path):
    store = ProfileStore(tmp_path)
    store.save(Profile("Default"))
    store.save(Profile("COD", package=COD))
    assert store.find_by_package(COD) == "COD"
    assert store.find_by_package("com.unknown") is None
    assert store.find_by_package("") is None


def test_linking_moves_the_link_from_other_profiles(tmp_path):
    store = ProfileStore(tmp_path)
    a, b = Profile("A", package=COD), Profile("B")
    store.save(a)
    store.save(b)
    unlinked = store.link_package(b, COD)
    assert unlinked == ["A"] and store.find_by_package(COD) == "B"
    assert store.load("A").package == "" and store.load("B").package == COD


def test_profile_to_load(tmp_path):
    store = ProfileStore(tmp_path)
    cod = Profile("COD", package=COD)
    store.save(cod)
    other = Profile("Default")
    assert profile_to_load(store, COD, other) == "COD"
    assert profile_to_load(store, COD, cod) is None                 # already loaded
    assert profile_to_load(store, "com.android.settings", other) is None
    assert profile_to_load(store, COD, None) == "COD"


def test_mapping_stops_only_when_leaving_the_linked_game():
    cod = Profile("COD", package=COD)
    assert should_stop_mapping(cod, "com.android.launcher3") is True
    assert should_stop_mapping(cod, COD) is False
    assert should_stop_mapping(Profile("unlinked"), "com.android.launcher3") is False   # unlinked: user's call
    assert should_stop_mapping(cod, "") is False
    assert should_stop_mapping(None, COD) is False
