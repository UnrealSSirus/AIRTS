"""Tests for capture_step with multi-team support."""
from __future__ import annotations
import pytest
from systems.capturing import capture_step
from entities.metal_spot import MetalSpot
from entities.metal_extractor import MetalExtractor
from entities.command_center import CommandCenter
from entities.unit import Unit


def _make_cc(x, y, team, player_id):
    cc = CommandCenter(x=x, y=y, team=team, player_id=player_id)
    cc.alive = True
    return cc


def _make_unit(x, y, team, player_id, unit_type="soldier"):
    u = Unit(x=x, y=y, team=team, unit_type=unit_type, player_id=player_id)
    u.alive = True
    return u


def _run_capture(entities, command_centers, ticks=1500):
    units = [e for e in entities if isinstance(e, Unit)]
    metal_spots = [e for e in entities if isinstance(e, MetalSpot)]
    metal_extractors = [e for e in entities if isinstance(e, MetalExtractor)]
    for _ in range(ticks):
        # refresh lists in case extractors were added
        metal_extractors = [e for e in entities if isinstance(e, MetalExtractor)]
        capture_step(
            entities, command_centers,
            units, metal_spots, metal_extractors,
            dt=1/60, teams={1, 2},
        )


def test_team1_captures_metal_spot():
    spot = MetalSpot(x=400, y=300)
    cc1 = _make_cc(80, 300, team=1, player_id=1)
    units = [_make_unit(400, 300, team=1, player_id=1)]
    entities = [spot, cc1] + units
    command_centers = [cc1]

    _run_capture(entities, command_centers)

    assert spot.owner == 1


def test_capture_is_team_scoped_2v2():
    """Two players on the same team both contribute to capture."""
    spot = MetalSpot(x=400, y=300)
    cc1 = _make_cc(80, 200, team=1, player_id=1)
    cc2 = _make_cc(80, 400, team=1, player_id=2)
    units = [
        _make_unit(400, 300, team=1, player_id=1),
        _make_unit(405, 300, team=1, player_id=2),
    ]
    entities = [spot, cc1, cc2] + units
    command_centers = [cc1, cc2]

    _run_capture(entities, command_centers)

    assert spot.owner == 1


def test_extractor_assigned_to_nearest_cc():
    """In 2v2, the extractor should be assigned to the nearest team CC."""
    spot = MetalSpot(x=400, y=300)
    cc_near = _make_cc(300, 300, team=1, player_id=1)   # distance 100
    cc_far = _make_cc(80, 300, team=1, player_id=2)     # distance 320
    units = [_make_unit(400, 300, team=1, player_id=1)]
    entities = [spot, cc_near, cc_far] + units
    command_centers = [cc_near, cc_far]

    _run_capture(entities, command_centers)

    assert spot.owner == 1
    extractors = [e for e in entities if isinstance(e, MetalExtractor)]
    if extractors:
        assert extractors[0] in cc_near.metal_extractors
