"""AI Arena — Elo-rated round-robin tournament system.

Runs headless games in parallel via ProcessPoolExecutor and tracks
Elo ratings in ai_arena/arena_ratings.json.  Error logs and tournament
summaries are written to ai_arena/logs/.
"""
from __future__ import annotations

import json
import os
import traceback
from concurrent.futures import ProcessPoolExecutor, Future
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class AIRecord:
    rating: float = 1000.0
    wins: int = 0
    losses: int = 0
    draws: int = 0

    @property
    def games(self) -> int:
        return self.wins + self.losses + self.draws

    def to_dict(self) -> dict:
        return {"rating": self.rating, "wins": self.wins,
                "losses": self.losses, "draws": self.draws}

    @classmethod
    def from_dict(cls, d: dict) -> AIRecord:
        return cls(rating=d.get("rating", 1000.0),
                   wins=d.get("wins", 0),
                   losses=d.get("losses", 0),
                   draws=d.get("draws", 0))


@dataclass
class MatchResult:
    ai1_id: str = ""
    ai2_id: str = ""
    winner: int = 0  # winning team_id, -1 = draw, 0 = error
    ticks: int = 0
    avg_step_ms: float = 0.0
    replay_path: str = ""
    error: str = ""
    error_traceback: str = ""
    error_log_path: str = ""
    match_index: int = -1
    match_format: str = "1v1"
    # N-player fields
    participants: list[tuple[str, int]] = field(default_factory=list)  # [(ai_id, team_id)]
    contributions: dict[int, float] = field(default_factory=dict)  # team_id → score


@dataclass
class TournamentProgress:
    total: int = 0
    completed: int = 0
    results: list[MatchResult] = field(default_factory=list)
    done: bool = False
    matchups: list[list[tuple[str, int]]] = field(default_factory=list)  # each: [(ai_id, team_id), ...]
    active_match_indices: list[int] = field(default_factory=list)
    match_format: str = "1v1"


# ---------------------------------------------------------------------------
# Elo Tracker
# ---------------------------------------------------------------------------

from core.paths import app_path
_ARENA_DIR = app_path("ai_arena")
_RATINGS_PATH = os.path.join(_ARENA_DIR, "arena_ratings.json")
_REPLAYS_DIR = os.path.join(_ARENA_DIR, "replays")
_LOGS_DIR = os.path.join(_ARENA_DIR, "logs")
_K = 32


# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------

def _write_error_log(
    participants: list[tuple[str, int]], error_msg: str, tb: str,
) -> str:
    """Write an error log for a failed match. Returns the filepath."""
    os.makedirs(_LOGS_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    ids = "_vs_".join(aid for aid, _ in participants[:4])
    filename = f"error_{ids}_{ts}.log"
    filepath = os.path.join(_LOGS_DIR, filename)
    match_desc = " vs ".join(f"{aid}(t{tid})" for aid, tid in participants)
    lines = [
        "AIRTS Arena Match Error",
        f"Time: {datetime.now().isoformat(timespec='seconds')}",
        f"Match: {match_desc}",
        "=" * 60,
        error_msg.rstrip(),
        "",
        "Traceback:",
        tb.rstrip(),
    ]
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return filepath


def write_tournament_summary(
    results: list[MatchResult],
    elo_tracker: EloTracker,
    pre_ratings: dict[str, float],
    ai_names: dict[str, str],
    start_time: float,
) -> str:
    """Write a tournament summary log. Returns the filepath."""
    import time as _time
    os.makedirs(_LOGS_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filepath = os.path.join(_LOGS_DIR, f"tournament_result_{ts}.log")

    elapsed = _time.time() - start_time
    mins = int(elapsed) // 60
    secs = int(elapsed) % 60

    errors = sum(1 for r in results if r.winner == 0)
    lines: list[str] = [
        "AIRTS Arena Tournament Summary",
        f"Date: {datetime.now().isoformat(timespec='seconds')}",
        f"Duration: {mins}m {secs}s",
        f"Total matches: {len(results)} ({errors} errors)",
        "",
        "=" * 60,
        "Final Elo Ratings (with deltas)",
        "=" * 60,
    ]

    for ai_id, record in elo_tracker.get_leaderboard():
        name = ai_names.get(ai_id, ai_id)
        old = pre_ratings.get(ai_id, 1000.0)
        delta = record.rating - old
        sign = "+" if delta >= 0 else ""
        lines.append(
            f"  {name:<20s}  Elo: {record.rating:7.1f}  ({sign}{delta:.1f})  "
            f"W:{record.wins} L:{record.losses} D:{record.draws}"
        )

    lines.append("")
    lines.append("=" * 60)
    lines.append("Per-Match Results")
    lines.append("=" * 60)
    for i, r in enumerate(results, 1):
        if r.participants:
            match_desc = _format_match_desc(r.participants, ai_names)
        else:
            match_desc = f"{ai_names.get(r.ai1_id, r.ai1_id)} vs {ai_names.get(r.ai2_id, r.ai2_id)}"
        if r.winner > 0:
            # Find winner AI name(s)
            winner_ids = [aid for aid, tid in r.participants if tid == r.winner] if r.participants else []
            if winner_ids:
                outcome = f"Team {r.winner} ({', '.join(ai_names.get(a, a) for a in winner_ids)}) wins"
            else:
                outcome = f"Team {r.winner} wins"
        elif r.winner == -1:
            outcome = "Draw"
        else:
            outcome = "Error"
        secs_game = r.ticks / 60.0
        m = int(secs_game) // 60
        s = int(secs_game) % 60
        lines.append(f"  {i:3d}. {match_desc}  ->  {outcome}  ({m}:{s:02d})")

    # Per-bot summary
    bot_stats: dict[str, dict[str, int]] = {}
    for r in results:
        all_aids = [aid for aid, _ in r.participants] if r.participants else [r.ai1_id, r.ai2_id]
        for aid in all_aids:
            if aid not in bot_stats:
                bot_stats[aid] = {"wins": 0, "losses": 0, "draws": 0, "errors": 0}
        if r.winner == 0:
            for aid in all_aids:
                bot_stats[aid]["errors"] += 1
        elif r.winner == -1:
            for aid in all_aids:
                bot_stats[aid]["draws"] += 1
        else:
            winner_aids = {aid for aid, tid in r.participants if tid == r.winner} if r.participants else set()
            for aid in all_aids:
                if aid in winner_aids:
                    bot_stats[aid]["wins"] += 1
                else:
                    bot_stats[aid]["losses"] += 1

    lines.append("")
    lines.append("=" * 60)
    lines.append("Per-Bot Summary (this tournament)")
    lines.append("=" * 60)
    for aid, s in sorted(bot_stats.items()):
        name = ai_names.get(aid, aid)
        total = s["wins"] + s["losses"] + s["draws"] + s["errors"]
        lines.append(
            f"  {name:<20s}  W:{s['wins']} L:{s['losses']} D:{s['draws']} "
            f"E:{s['errors']}  Total:{total}"
        )

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return filepath


def _format_match_desc(
    participants: list[tuple[str, int]],
    ai_names: dict[str, str],
) -> str:
    """Human-readable match description from participants list."""
    teams: dict[int, list[str]] = {}
    for aid, tid in participants:
        teams.setdefault(tid, []).append(ai_names.get(aid, aid))
    sorted_teams = sorted(teams.items())
    if len(sorted_teams) == 2 and all(len(v) == 1 for _, v in sorted_teams):
        return f"{sorted_teams[0][1][0]} vs {sorted_teams[1][1][0]}"
    if all(len(v) == 1 for _, v in sorted_teams):
        return " | ".join(v[0] for _, v in sorted_teams)
    return " vs ".join("+".join(v) for _, v in sorted_teams)


class EloTracker:
    """Manages Elo ratings with JSON persistence."""

    def __init__(self):
        self.records: dict[str, AIRecord] = {}

    def load(self) -> None:
        if os.path.isfile(_RATINGS_PATH):
            try:
                with open(_RATINGS_PATH, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                if isinstance(raw, dict):
                    self.records = {k: AIRecord.from_dict(v)
                                    for k, v in raw.items()}
            except (json.JSONDecodeError, ValueError, TypeError):
                self.records = {}

    def save(self) -> None:
        os.makedirs(_ARENA_DIR, exist_ok=True)
        with open(_RATINGS_PATH, "w", encoding="utf-8") as f:
            json.dump({k: v.to_dict() for k, v in self.records.items()}, f, indent=2)

    def ensure(self, ai_id: str) -> None:
        if ai_id not in self.records:
            self.records[ai_id] = AIRecord()

    def update(self, ai_a: str, ai_b: str, winner: int) -> None:
        """Update ratings after a match.

        winner: 1 = ai_a won, 2 = ai_b won, -1 = draw.
        """
        self.ensure(ai_a)
        self.ensure(ai_b)
        ra = self.records[ai_a].rating
        rb = self.records[ai_b].rating

        ea = 1.0 / (1.0 + 10.0 ** ((rb - ra) / 400.0))
        eb = 1.0 - ea

        if winner == 1:
            sa, sb = 1.0, 0.0
            self.records[ai_a].wins += 1
            self.records[ai_b].losses += 1
        elif winner == 2:
            sa, sb = 0.0, 1.0
            self.records[ai_a].losses += 1
            self.records[ai_b].wins += 1
        else:
            sa, sb = 0.5, 0.5
            self.records[ai_a].draws += 1
            self.records[ai_b].draws += 1

        self.records[ai_a].rating = ra + _K * (sa - ea)
        self.records[ai_b].rating = rb + _K * (sb - eb)

    def reset(self) -> None:
        self.records.clear()
        if os.path.isfile(_RATINGS_PATH):
            os.remove(_RATINGS_PATH)

    def compute_delta(self, ai_a: str, ai_b: str, winner: int,
                       ratings_snapshot: dict[str, float] | None = None,
                       ) -> tuple[float, float]:
        """Compute Elo deltas without applying them. Returns (delta_a, delta_b)."""
        if ratings_snapshot:
            ra = ratings_snapshot.get(ai_a, 1000.0)
            rb = ratings_snapshot.get(ai_b, 1000.0)
        else:
            self.ensure(ai_a)
            self.ensure(ai_b)
            ra = self.records[ai_a].rating
            rb = self.records[ai_b].rating

        ea = 1.0 / (1.0 + 10.0 ** ((rb - ra) / 400.0))
        eb = 1.0 - ea

        if winner == 1:
            sa, sb = 1.0, 0.0
        elif winner == 2:
            sa, sb = 0.0, 1.0
        else:
            sa, sb = 0.5, 0.5

        return (_K * (sa - ea), _K * (sb - eb))

    def update_ffa(self, participants: list[tuple[str, int]], winner_team: int,
                   contributions: dict[int, float] | None = None) -> None:
        """Update ratings for a FFA match (each player = own team).

        Uses pairwise Elo with K/(N-1) scaling.  Losers' penalties are
        weighted by contribution rank: high-impact losers lose less.
        """
        n = len(participants)
        if n < 2:
            return
        k = _K / max(n - 1, 1)

        for aid, _ in participants:
            self.ensure(aid)

        if winner_team == -1:
            # Draw — everyone gets 0.5 pairwise
            for aid, _ in participants:
                self.records[aid].draws += 1
            for i, (ai, ti) in enumerate(participants):
                for j, (aj, tj) in enumerate(participants):
                    if j <= i:
                        continue
                    ra = self.records[ai].rating
                    rb = self.records[aj].rating
                    ea = 1.0 / (1.0 + 10.0 ** ((rb - ra) / 400.0))
                    self.records[ai].rating += k * (0.5 - ea)
                    self.records[aj].rating += k * (0.5 - (1.0 - ea))
            return

        winner_ids = [aid for aid, tid in participants if tid == winner_team]
        losers = [(aid, tid) for aid, tid in participants if tid != winner_team]
        n_losers = len(losers)

        # Rank losers by contribution (descending) for penalty weighting
        if contributions and n_losers > 1:
            losers_sorted = sorted(losers, key=lambda x: contributions.get(x[1], 0), reverse=True)
            loser_factors: dict[str, float] = {}
            for rank, (aid, _) in enumerate(losers_sorted):
                if n_losers <= 1:
                    loser_factors[aid] = 1.0
                else:
                    # rank 0 = highest contrib → factor 0.5 (less loss)
                    # rank n-1 = lowest contrib → factor 1.5 (more loss)
                    loser_factors[aid] = 0.5 + rank * 1.0 / (n_losers - 1)
        else:
            loser_factors = {aid: 1.0 for aid, _ in losers}

        # Pairwise: each winner vs each loser
        for w_id in winner_ids:
            for l_id, _ in losers:
                ra = self.records[w_id].rating
                rb = self.records[l_id].rating
                ea = 1.0 / (1.0 + 10.0 ** ((rb - ra) / 400.0))
                self.records[w_id].rating += k * (1.0 - ea)
                self.records[l_id].rating += k * (0.0 - (1.0 - ea)) * loser_factors.get(l_id, 1.0)
            self.records[w_id].wins += 1

        for l_id, _ in losers:
            self.records[l_id].losses += 1

    def update_2v2(self, participants: list[tuple[str, int]], winner_team: int,
                   contributions: dict[int, float] | None = None) -> None:
        """Update ratings for a 2v2 match.

        Team Elo = average of members.  Within each team, Elo change is
        scaled by contribution: winners with high contribution gain more,
        losers with high contribution lose less.
        """
        teams: dict[int, list[str]] = {}
        for aid, tid in participants:
            self.ensure(aid)
            teams.setdefault(tid, []).append(aid)

        team_ids = sorted(teams.keys())
        if len(team_ids) != 2:
            return

        ta, tb = team_ids
        avg_a = sum(self.records[a].rating for a in teams[ta]) / len(teams[ta])
        avg_b = sum(self.records[a].rating for a in teams[tb]) / len(teams[tb])
        ea = 1.0 / (1.0 + 10.0 ** ((avg_b - avg_a) / 400.0))

        if winner_team == -1:
            sa, sb = 0.5, 0.5
            for aid in teams[ta] + teams[tb]:
                self.records[aid].draws += 1
        elif winner_team == ta:
            sa, sb = 1.0, 0.0
            for aid in teams[ta]:
                self.records[aid].wins += 1
            for aid in teams[tb]:
                self.records[aid].losses += 1
        elif winner_team == tb:
            sa, sb = 0.0, 1.0
            for aid in teams[tb]:
                self.records[aid].wins += 1
            for aid in teams[ta]:
                self.records[aid].losses += 1
        else:
            return

        base_a = _K * (sa - ea)
        base_b = _K * (sb - (1.0 - ea))

        # Distribute within teams, scaled by contribution
        for tid, base_delta in [(ta, base_a), (tb, base_b)]:
            members = teams[tid]
            if len(members) == 1 or not contributions:
                for aid in members:
                    self.records[aid].rating += base_delta
                continue
            # Compute contribution shares
            contribs = [max(contributions.get(tid, 0), 0) for _ in members]
            # All members on same team share the same team-level contribution
            # Use per-player contribution if available (future), else equal split
            total_c = sum(contribs)
            if total_c <= 0:
                for aid in members:
                    self.records[aid].rating += base_delta
                continue
            for i, aid in enumerate(members):
                share = contribs[i] / total_c  # 0..1
                is_winner = (base_delta > 0)
                if is_winner:
                    factor = 0.5 + share * len(members)  # rescaled
                else:
                    factor = 0.5 + (1.0 - share) * len(members)  # inverted for losers
                # Normalize so average factor = 1.0
                self.records[aid].rating += base_delta * factor

    def get_leaderboard(self) -> list[tuple[str, AIRecord]]:
        return sorted(self.records.items(), key=lambda t: t[1].rating, reverse=True)


# ---------------------------------------------------------------------------
# Worker function (top-level, picklable)
# ---------------------------------------------------------------------------

def _run_arena_game(
    participants: list[tuple[str, int]],
    match_index: int,
    map_width: int,
    map_height: int,
    obstacle_count: tuple[int, int],
    max_ticks: int,
) -> MatchResult:
    """Run a single headless game in a worker process. Returns MatchResult."""
    import os as _os
    _os.environ["SDL_VIDEODRIVER"] = "dummy"

    import pygame as _pg
    _pg.init()
    _pg.display.set_mode((1, 1))

    # Backward-compat: extract ai1/ai2 for legacy fields
    ai1_id = participants[0][0] if participants else ""
    ai2_id = participants[1][0] if len(participants) > 1 else ""
    match_format = "1v1"
    team_set = {tid for _, tid in participants}
    if len(team_set) == 2:
        team_sizes = {}
        for _, tid in participants:
            team_sizes[tid] = team_sizes.get(tid, 0) + 1
        if any(v > 1 for v in team_sizes.values()):
            match_format = "2v2"
    elif len(team_set) > 2:
        match_format = "ffa"

    try:
        from systems.ai import AIRegistry
        from systems.map_generator import DefaultMapGenerator
        from game import Game

        registry = AIRegistry()
        registry.discover()

        needed = {aid for aid, _ in participants}
        registered = {aid for aid, _ in registry.get_choices()}
        if not needed.issubset(registered):
            import time as _time
            _time.sleep(0.1)
            registry = AIRegistry()
            registry.discover()

        # Build player_ai and player_team from participants
        player_ai = {}
        player_team = {}
        ai_ids_map = {}
        ai_names_map = {}
        for pid_idx, (aid, tid) in enumerate(participants):
            pid = pid_idx + 1
            ai_obj = registry.create(aid)
            player_ai[pid] = ai_obj
            player_team[pid] = tid
            ai_ids_map[pid] = aid
            ai_names_map[pid] = ai_obj.ai_name

        replay_config = {
            "player_ai_ids": ai_ids_map,
            "player_ai_names": ai_names_map,
            "player_team": player_team,
            "obstacle_count": list(obstacle_count),
            "player_name": "Arena",
        }

        game = Game(
            width=map_width,
            height=map_height,
            map_generator=DefaultMapGenerator(obstacle_count=obstacle_count),
            player_ai=player_ai,
            player_team=player_team,
            screen=_pg.display.get_surface(),
            clock=_pg.time.Clock(),
            replay_config=replay_config,
            headless=True,
            max_ticks=max_ticks,
            save_replay=True,
            step_timeout_ms=100,
            replay_output_dir=_REPLAYS_DIR,
        )

        result = game.run()
        winner = result.get("winner", 0)
        ticks = game._iteration
        replay_path = result.get("replay_filepath", "")

        avg_step_ms = 0.0
        stats = result.get("stats")
        if stats and stats.get("step_ms"):
            step_ms_list = stats["step_ms"]
            avg_step_ms = sum(step_ms_list) / len(step_ms_list)

        # Extract per-team contribution scores from stats
        contributions: dict[int, float] = {}
        if stats and "final" in stats:
            for tid_str, team_final in stats["final"].items():
                tid = int(tid_str)
                contributions[tid] = (
                    team_final.get("damage_dealt", 0)
                    + team_final.get("units_killed", 0) * 50
                    + team_final.get("metal_spots_captured", 0) * 100
                )

        return MatchResult(
            ai1_id=ai1_id, ai2_id=ai2_id, winner=winner, ticks=ticks,
            avg_step_ms=avg_step_ms, replay_path=replay_path,
            match_index=match_index, match_format=match_format,
            participants=list(participants), contributions=contributions,
        )

    except Exception as exc:
        tb = traceback.format_exc()
        error_log = _write_error_log(participants, str(exc), tb)
        return MatchResult(
            ai1_id=ai1_id, ai2_id=ai2_id, winner=0, error=str(exc),
            error_traceback=tb, error_log_path=error_log,
            match_index=match_index, match_format=match_format,
            participants=list(participants),
        )

    finally:
        _pg.quit()


# ---------------------------------------------------------------------------
# Arena Runner
# ---------------------------------------------------------------------------

def _distribute_matchups(
    matchups: list[tuple[list[tuple[str, int]], int]], n_workers: int,
) -> list[list[tuple[list[tuple[str, int]], int]]]:
    """Greedy bot-aware assignment of matchups to worker queues.

    Each entry is (participants, match_index).  Assigns each matchup to
    the worker whose queue has the fewest matches involving any participating bot,
    tiebreak by shortest queue.
    """
    queues: list[list[tuple[list[tuple[str, int]], int]]] = [[] for _ in range(n_workers)]
    bot_counts: list[dict[str, int]] = [{} for _ in range(n_workers)]

    for parts, idx in matchups:
        aids = [aid for aid, _ in parts]
        best_w = 0
        best_score = (float("inf"), float("inf"))
        for w in range(n_workers):
            overlap = sum(bot_counts[w].get(a, 0) for a in aids)
            score = (overlap, len(queues[w]))
            if score < best_score:
                best_score = score
                best_w = w
        queues[best_w].append((parts, idx))
        for a in aids:
            bot_counts[best_w][a] = bot_counts[best_w].get(a, 0) + 1

    return queues


class ArenaRunner:
    """Orchestrates a round-robin tournament using a process pool with
    slot-based submission (one match per worker at a time)."""

    def __init__(self):
        self._executor: ProcessPoolExecutor | None = None
        self._results: list[MatchResult] = []
        self._total: int = 0
        self._running: bool = False
        self._matchups: list[list[tuple[str, int]]] = []  # each: [(ai_id, team_id), ...]
        self._match_format: str = "1v1"

        # Slot-based state
        self._worker_queues: list[list[tuple[list[tuple[str, int]], int]]] = []
        self._active_futures: dict[int, tuple[Future, int]] = {}  # slot -> (future, match_index)
        self._n_workers: int = 0

        # Game params stored for _submit_next
        self._map_width: int = 800
        self._map_height: int = 600
        self._obstacle_count: tuple[int, int] = (4, 8)
        self._max_ticks: int = 54000

    @property
    def running(self) -> bool:
        return self._running

    def start(
        self,
        ai_ids: list[str],
        rounds: int = 1,
        workers: int = 4,
        map_width: int = 800,
        map_height: int = 600,
        obstacle_count: tuple[int, int] = (4, 8),
        max_ticks: int = 54000,
        match_format: str = "1v1",
    ) -> None:
        """Generate matchups based on format, distribute to worker queues, start."""
        if self._running:
            return

        self._match_format = match_format

        # Build matchup list based on format
        matchups: list[list[tuple[str, int]]] = []

        if match_format == "ffa":
            # All AIs in one match, each on their own team
            base = [(aid, i + 1) for i, aid in enumerate(ai_ids)]
            for _ in range(rounds):
                matchups.append(list(base))

        elif match_format == "2v2":
            from itertools import combinations
            # Generate all valid 2v2 team pairings
            team_combos = list(combinations(range(len(ai_ids)), 2))
            for i, combo_a in enumerate(team_combos):
                for combo_b in team_combos[i + 1:]:
                    if set(combo_a) & set(combo_b):
                        continue  # skip if same AI on both teams
                    parts = [
                        (ai_ids[combo_a[0]], 1), (ai_ids[combo_a[1]], 1),
                        (ai_ids[combo_b[0]], 2), (ai_ids[combo_b[1]], 2),
                    ]
                    for _ in range(rounds):
                        matchups.append(parts)

        else:
            # 1v1 round-robin: each pair plays both sides × rounds
            for i, a in enumerate(ai_ids):
                for b in ai_ids[i + 1:]:
                    for _ in range(rounds):
                        matchups.append([(a, 1), (b, 2)])
                        matchups.append([(b, 1), (a, 2)])

        self._matchups = matchups
        self._total = len(matchups)
        self._results = []
        self._running = True
        self._n_workers = min(workers, max(self._total, 1))

        # Store game params
        self._map_width = map_width
        self._map_height = map_height
        self._obstacle_count = obstacle_count
        self._max_ticks = max_ticks

        # Distribute into per-worker queues
        indexed = [(parts, idx) for idx, parts in enumerate(matchups)]
        self._worker_queues = _distribute_matchups(indexed, self._n_workers)
        self._active_futures = {}

        self._executor = ProcessPoolExecutor(max_workers=self._n_workers)
        for slot in range(self._n_workers):
            self._submit_next(slot)

    def _submit_next(self, slot: int) -> None:
        """Pop next matchup from this worker's queue and submit it."""
        if not self._worker_queues[slot]:
            return
        participants, match_index = self._worker_queues[slot].pop(0)
        fut = self._executor.submit(
            _run_arena_game, participants, match_index,
            self._map_width, self._map_height,
            self._obstacle_count, self._max_ticks,
        )
        self._active_futures[slot] = (fut, match_index)

    def poll(self) -> TournamentProgress:
        """Non-blocking progress check. Call each frame."""
        if not self._running:
            return TournamentProgress(
                done=True, results=self._results,
                total=self._total, completed=len(self._results),
                matchups=self._matchups, match_format=self._match_format,
            )

        # Check active futures for completion
        completed_slots: list[int] = []
        for slot, (fut, match_index) in list(self._active_futures.items()):
            if fut.done():
                try:
                    result = fut.result()
                except Exception as exc:
                    parts = self._matchups[match_index]
                    result = MatchResult(
                        winner=0, error=str(exc), match_index=match_index,
                        participants=list(parts), match_format=self._match_format,
                    )
                self._results.append(result)
                completed_slots.append(slot)

        # Chain next matches for completed slots
        for slot in completed_slots:
            del self._active_futures[slot]
            self._submit_next(slot)

        # Done when all queues empty and no active futures
        done = (not self._active_futures and
                all(len(q) == 0 for q in self._worker_queues))
        if done:
            self._running = False
            if self._executor is not None:
                self._executor.shutdown(wait=False)
                self._executor = None

        active_indices = [mi for _, mi in self._active_futures.values()]

        return TournamentProgress(
            total=self._total,
            completed=len(self._results),
            results=list(self._results),
            done=done,
            matchups=self._matchups,
            active_match_indices=active_indices,
            match_format=self._match_format,
        )

    def cancel(self) -> None:
        """Cancel remaining futures and shut down."""
        for fut, _ in self._active_futures.values():
            fut.cancel()
        self._active_futures.clear()
        self._worker_queues = []
        self._running = False
        if self._executor is not None:
            self._executor.shutdown(wait=False, cancel_futures=True)
            self._executor = None
