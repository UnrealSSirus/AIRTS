from __future__ import annotations
from collections import namedtuple
from enum import StrEnum
import math
import random

import pygame
from pygame.math import Vector2
from config.unit_types import get_spawnable_types
from entities.metal_spot import MetalSpot
from entities.unit import Unit
from systems.ai.base import BaseAI

def _build_unit_id_map(units:list[Unit]):
    _map = {unit.entity_id:unit for unit in units}
    return _map

def _pos(unit:Unit):
    return Vector2(unit.x, unit.y)

class Peri(BaseAI):
    """My own bot.

    Spams snipers and medics in a 4:1 ratio
    Increase medic portion more if sniper hp collectively falls below 70%

    Build order:
        sniper 1 (S1) -> 1st nearest mex (M1)
        S2 -> M1
        when M1 finishes: S1, S2 -> M2
        S3 -> M2
        (Move new snipers to nearest unclaimed mex from now on)
        S4 deny nearest enemy mex
        Medic 1 -> guard S4
        S5

        Attempt capture enemy mex
        Maintain front and push using micro logic
        
    Micro:
        Different modes: push, retreat, combat
        Medics in back, snipers in front
        each step, select target sniper with most hp > sniper damage

    """

    ai_id = "Peri"
    ai_name = "Peri AI"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.build_order = ['sniper', 'sniper', 'sniper', 'sniper', 'medic']

        self.old_units = {}
        self.cur_units = {}

        self.new_units = {}
        self.destroyed_units = {}

        self.old_enemy_positions = {}
        self.new_enemy_positions = {}
        self.enemy_velocities = {}
        self.enemy_predictions = {}
        
        self.entity_info:dict[int, tuple[Unit, set[str], float]] = {}  # {id: (Unit obj, flags, team score)}

        self.team_target = None
        self.team_center = Vector2(0, 0)
        self.team_target_radius = 0

        self.target_medic_ratio = 0.2
        self.num_medics = 0
        self.num_snipers = 0

        self.mid = self.bounds[0] / 2

    def on_start(self) -> None:
        self.set_build("sniper")
        self.region = (0, self.mid) if _pos(self.get_cc()).x < self.mid else (self.mid, self.bounds[0])

    def on_step(self, iteration: int) -> None:
        self.setup_step()
        self.calculate_diffs()

        self.handle_built_units()
        self.handle_destroyed_units()

        self.handle_build()
        self.handle_micro()

    def handle_build(self):
        if self.build_order:
            self.set_build(self.build_order[0])
            return

        cur_medic_ratio = (self.num_medics + self.num_snipers) / self.num_medics

        if cur_medic_ratio >= self.target_medic_ratio:
            self.set_build('sniper')
        else:
            self.set_build('medic')

    def handle_macro(self):
        self.team_target_radius = math.sqrt(len(self.get_own_mobile_units()))

        (
            # short cutting lets only one target
            self.target_metal_spots() or
            self.target_enemies()
        )

    def handle_micro(self):
        pass

    def move_units_to_target(self):
        if self.team_target is None:
            return
        
        for unit in self.get_own_mobile_units():
            pos = _pos(unit)
            if pos.distance_to(self.team_target) > self.team_target_radius:
                self.move_unit(unit, self.team_target.x, self.team_target.y)

    def in_our_half(self, pos:Vector2):
        return self.region[0] <= pos.x <= self.region[1]

    def get_metal_spot_flag(self, metal_spot:MetalSpot):
        pos = _pos(metal_spot)
        if self.in_our_half(pos):
            flag = {'near'}
        else:
            flag = {'far'}
        
        if metal_spot.owner is None:
            flag |= {'neutral'}
        elif metal_spot.owner == self._team:
            flag |= {'ours'}
        else:
            flag |= {'enemy'}

        return flag

    def get_enemy_flag(self, enemy:Unit):
        pos = _pos(enemy)
        flag = {'enemy'}
        if self.in_our_half(pos):
            flag |= {'near'}
        else:
            flag |= {'far'}

        return flag

    def get_metal_spot_flags(self) -> list[tuple[float, MetalSpot]]:
        for metal_spot in self.get_metal_spots():
            flag = self.get_metal_spot_flag(metal_spot)
            pass

            


    def get_enemy_scores(self):
        pass


    def setup_step(self):
        self.old_units = self.cur_units
        self.cur_units = _build_unit_id_map(self.get_units())

        self.new_units = {}
        self.destroyed_units = {}

        self.old_enemy_positions = self.new_enemy_positions
        self.new_enemy_positions = {uid:_pos(unit) for uid, unit in self.cur_units.items() if unit.team != self._team}
        self.solve_vels_and_preds()
        
        mobile_units = self.get_own_mobile_units()
        if len(mobile_units) > 0:
            self.team_center = sum(_pos(unit) for unit in mobile_units) / len(mobile_units)
        else:
            self.team_center = self.get_cc()

    def solve_vels_and_preds(self):
        for uid, new_pos in self.new_enemy_positions.items():
            if uid in self.old_enemy_positions:
                old_pos = self.old_enemy_positions[uid]
                
                vel = new_pos - old_pos
                pred = new_pos + vel

                self.enemy_velocities[uid] = vel
                self.enemy_predictions[uid] = pred


    def calculate_diffs(self):
        for uid, unit in self.cur_units.items():
            if uid not in self.old_units:
                self.new_units[uid] = unit
        
        for uid, unit in self.old_units.items():
            if uid not in self.cur_units:
                self.destroyed_units[uid] = unit

    def handle_built_units(self):
        for uid, unit in self.new_units.items():
            self.on_unit_built(uid, unit)

    def handle_destroyed_units(self):
        for uid, unit in self.destroyed_units.items():
            self.on_unit_destroyed(uid, unit)

    def on_unit_built(self, uid:int, unit:Unit):
        # update ratio and target
        if unit.team == self._team:
            if unit.unit_type == 'medic':
                self.num_medics += 1
            elif unit.unit_type == 'sniper':
                self.num_snipers += 1
            
            if self.build_order:
                self.build_order.pop(0)

    def on_unit_destroyed(self, uid:int, unit:Unit):
        if unit.team == self._team:
            if unit.unit_type == 'medic':
                self.num_medics -= 1
            elif unit.unit_type == 'sniper':
                self.num_snipers -= 1
            