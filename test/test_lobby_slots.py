"""Tests for dynamic lobby slot logic in CreateLobbyScreen."""
from __future__ import annotations
import pygame
import pytest

# conftest.py ensures SDL_VIDEODRIVER=dummy and pygame.init()


def _make_screen():
    return pygame.display.set_mode((1280, 720), flags=pygame.NOFRAME)


@pytest.fixture(autouse=True)
def clean_settings(tmp_path, monkeypatch):
    """Ensure each test starts with no saved lobby settings."""
    import screens.create_lobby as cl_module
    monkeypatch.setattr(cl_module, "_SETTINGS_PATH", str(tmp_path / "test_lobby.json"))


def _make_lobby(ai_choices=None):
    from screens.create_lobby import CreateLobbyScreen
    screen = _make_screen()
    clock = pygame.time.Clock()
    choices = ai_choices or [("easy", "Easy AI"), ("wander", "Wander AI")]
    return CreateLobbyScreen(screen, clock, choices)


class TestDefaultTwoSlots:
    def test_default_two_slots(self):
        lobby = _make_lobby()
        assert len(lobby._slots) == 2

    def test_p1_human_team1(self):
        lobby = _make_lobby()
        s0 = lobby._slots[0]
        assert s0.pid == 1
        assert s0.ai_dd.value == "human"
        assert int(s0.team_dd.value) == 1

    def test_p2_ai_team2(self):
        lobby = _make_lobby()
        s1 = lobby._slots[1]
        assert s1.pid == 2
        assert s1.ai_dd.value != "human"
        assert int(s1.team_dd.value) == 2


class TestAddSlot:
    def test_add_slot_increments_count(self):
        lobby = _make_lobby()
        lobby._add_slot()
        assert len(lobby._slots) == 3

    def test_add_slot_up_to_four(self):
        lobby = _make_lobby()
        lobby._add_slot()
        lobby._add_slot()
        assert len(lobby._slots) == 4

    def test_add_slot_capped_at_four(self):
        lobby = _make_lobby()
        for _ in range(10):
            lobby._add_slot()
        assert len(lobby._slots) == 4

    def test_new_slot_pid_is_sequential(self):
        lobby = _make_lobby()
        lobby._add_slot()
        assert lobby._slots[2].pid == 3


class TestRemoveSlot:
    def test_remove_slot_decrements_count(self):
        lobby = _make_lobby()
        lobby._add_slot()
        lobby._remove_slot(lobby._slots[2])
        assert len(lobby._slots) == 2

    def test_remove_slot_min_two(self):
        lobby = _make_lobby()
        lobby._remove_slot(lobby._slots[1])  # should do nothing
        assert len(lobby._slots) == 2

    def test_remove_slot_renumbers_pids(self):
        lobby = _make_lobby()
        lobby._add_slot()
        lobby._add_slot()
        # Remove P2 (index 1)
        lobby._remove_slot(lobby._slots[1])
        pids = [s.pid for s in lobby._slots]
        assert pids == [1, 2, 3]


class TestBuildResult:
    def test_build_result_1v1(self):
        lobby = _make_lobby()
        # Default: P1=human/team1, P2=ai/team2
        res = lobby._build_result()
        assert res.data["player_team"] == {1: 1, 2: 2}
        # P1 is human so not in player_ai_ids
        assert 1 not in res.data["player_ai_ids"]
        assert 2 in res.data["player_ai_ids"]

    def test_build_result_2v2(self):
        lobby = _make_lobby()
        lobby._add_slot()
        lobby._add_slot()
        # Manually set teams: P1,P2 = team1; P3,P4 = team2
        lobby._slots[0].team_dd.selected_index = 0  # team 1
        lobby._slots[1].team_dd.selected_index = 0  # team 1
        lobby._slots[2].team_dd.selected_index = 1  # team 2
        lobby._slots[3].team_dd.selected_index = 1  # team 2
        # All AI except P1 (human)
        lobby._slots[0].ai_dd.selected_index = 0  # human
        lobby._slots[1].ai_dd.selected_index = 1  # easy
        lobby._slots[2].ai_dd.selected_index = 1  # easy
        lobby._slots[3].ai_dd.selected_index = 1  # easy
        res = lobby._build_result()
        assert res.data["player_team"] == {1: 1, 2: 1, 3: 2, 4: 2}
        assert len(res.data["player_ai_ids"]) == 3  # P1 is human

    def test_build_result_1v3(self):
        lobby = _make_lobby()
        lobby._add_slot()
        lobby._add_slot()
        # P1=team1, P2..P4=team2
        lobby._slots[0].team_dd.selected_index = 0  # team 1
        for i in range(1, 4):
            lobby._slots[i].team_dd.selected_index = 1  # team 2
        res = lobby._build_result()
        pt = res.data["player_team"]
        assert pt[1] == 1
        assert pt[2] == 2
        assert pt[3] == 2
        assert pt[4] == 2


class TestPersistAndRestoreSlots:
    def test_persist_and_restore(self, tmp_path):
        # autouse fixture already set a tmp_path settings file;
        # use a different sub-path to explicitly control the saved file
        import screens.create_lobby as cl_module
        settings_file = tmp_path / "lobby_settings.json"
        original = cl_module._SETTINGS_PATH
        cl_module._SETTINGS_PATH = str(settings_file)
        try:
            lobby = _make_lobby()
            lobby._add_slot()
            lobby._persist_settings()
            lobby2 = _make_lobby()
            assert len(lobby2._slots) == 3
        finally:
            cl_module._SETTINGS_PATH = original

    def test_restore_same_ai_ids(self, tmp_path):
        import screens.create_lobby as cl_module
        import json
        settings_file = tmp_path / "lobby_settings2.json"
        original = cl_module._SETTINGS_PATH
        cl_module._SETTINGS_PATH = str(settings_file)
        try:
            settings = {
                "slots": [
                    {"ai_id": "human", "team": 1},
                    {"ai_id": "easy", "team": 2},
                    {"ai_id": "wander", "team": 2},
                ]
            }
            settings_file.write_text(json.dumps(settings))
            lobby = _make_lobby()
            assert len(lobby._slots) == 3
            assert lobby._slots[0].ai_dd.value == "human"
            assert lobby._slots[1].ai_dd.value == "easy"
            assert lobby._slots[2].ai_dd.value == "wander"
        finally:
            cl_module._SETTINGS_PATH = original
