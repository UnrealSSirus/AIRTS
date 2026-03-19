"""Tests for GameCommand player_id field and serialization."""
from __future__ import annotations
import pytest
from systems.commands import GameCommand


def test_game_command_has_player_id():
    cmd = GameCommand(type="move", player_id=1, tick=0, data={})
    assert cmd.player_id == 1


def test_game_command_no_team_field():
    cmd = GameCommand(type="move", player_id=1, tick=0, data={})
    assert not hasattr(cmd, "team")


def test_serialize_uses_player_id_key():
    cmd = GameCommand(type="stop", player_id=2, tick=5, data={"unit_ids": [1]})
    s = cmd.serialize()
    assert '"player_id"' in s
    assert '"team"' not in s


def test_deserialize_new_format():
    cmd = GameCommand(type="move", player_id=3, tick=10, data={"unit_ids": [7]})
    s = cmd.serialize()
    cmd2 = GameCommand.deserialize(s)
    assert cmd2.player_id == 3
    assert cmd2.type == "move"


def test_deserialize_legacy_team_key():
    """Old replays serialized with 'team' key must still deserialize."""
    import json
    legacy = json.dumps({"type": "stop", "team": 2, "tick": 1, "data": {}})
    cmd = GameCommand.deserialize(legacy)
    assert cmd.player_id == 2
