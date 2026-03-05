"""Entry point for AIRTS."""
from __future__ import annotations
import argparse
import sys


def main():
    parser = argparse.ArgumentParser(description="AIRTS — AI Real-Time Strategy")
    parser.add_argument("--headless", action="store_true",
                        help="Run in headless mode (AI vs AI, no rendering, auto-exit)")
    parser.add_argument("--team1", type=str, default=None,
                        help="AI id for team 1 (e.g. 'wander')")
    parser.add_argument("--team2", type=str, default=None,
                        help="AI id for team 2 (e.g. 'wander')")
    parser.add_argument("--width", type=int, default=800,
                        help="Map width (default: 800)")
    parser.add_argument("--height", type=int, default=600,
                        help="Map height (default: 600)")
    parser.add_argument("--obs-min", type=int, default=4,
                        help="Minimum obstacles (default: 4)")
    parser.add_argument("--obs-max", type=int, default=8,
                        help="Maximum obstacles (default: 8)")
    parser.add_argument("--time-limit", type=int, default=15,
                        help="Time limit in minutes, 0 for no limit (default: 15)")
    parser.add_argument("--list-ais", action="store_true",
                        help="List available AI ids and exit")

    args = parser.parse_args()

    if args.list_ais:
        from systems.ai import AIRegistry
        registry = AIRegistry()
        registry.discover()
        choices = registry.get_choices()
        if not choices:
            print("No AIs found.")
        else:
            for ai_id, ai_name in choices:
                print(f"  {ai_id:20s}  {ai_name}")
        sys.exit(0)

    if args.headless:
        _run_headless(args)
    else:
        from app import App
        try:
            App().run()
        except Exception as exc:
            from systems.crash_handler import log_crash
            path = log_crash(exc, context="fatal")
            print(f"[AIRTS] Fatal crash — log saved to {path}")


def _run_headless(args):
    """Run a headless AI-vs-AI game directly, then exit."""
    import pygame
    from systems.ai import AIRegistry
    from systems.map_generator import DefaultMapGenerator
    from game import Game

    registry = AIRegistry()
    registry.discover()
    choices = registry.get_choices()
    ai_ids = [c[0] for c in choices]

    # Default to first available AI if not specified
    t1_id = args.team1 or (ai_ids[0] if ai_ids else "wander")
    t2_id = args.team2 or (ai_ids[0] if ai_ids else "wander")

    for label, ai_id in [("team1", t1_id), ("team2", t2_id)]:
        if ai_id not in [c[0] for c in choices]:
            print(f"[AIRTS] Unknown AI '{ai_id}' for {label}. Use --list-ais to see options.")
            sys.exit(1)

    team_ai = {
        1: registry.create(t1_id),
        2: registry.create(t2_id),
    }

    obs = (args.obs_min, args.obs_max)
    max_ticks = args.time_limit * 60 * 60 if args.time_limit > 0 else 0

    pygame.init()
    pygame.mixer.init()
    screen = pygame.display.set_mode((args.width, args.height))
    pygame.display.set_caption("AIRTS — Headless")
    clock = pygame.time.Clock()

    team_ai_ids = {1: t1_id, 2: t2_id}
    replay_config = {
        "team_ai_ids": team_ai_ids,
        "team_ai_names": {t: ai.ai_name for t, ai in team_ai.items()},
        "obstacle_count": list(obs),
        "player_name": "Headless",
    }

    game = Game(
        width=args.width,
        height=args.height,
        map_generator=DefaultMapGenerator(obstacle_count=obs),
        team_ai=team_ai,
        screen=screen,
        clock=clock,
        replay_config=replay_config,
        player_name="Headless",
        headless=True,
        max_ticks=max_ticks,
    )

    try:
        result = game.run()
    except Exception as exc:
        from systems.crash_handler import log_crash
        path = log_crash(exc, context="headless")
        print(f"[AIRTS] Headless game crashed — log saved to {path}")
        sys.exit(1)

    winner = result.get("winner", 0)
    team_names = result.get("team_names", {})
    if winner > 0:
        print(f"[AIRTS] Winner: Team {winner} ({team_names.get(winner, '?')})")
    elif winner == -1:
        print("[AIRTS] Result: Draw")
    else:
        print("[AIRTS] Result: Undecided")

    pygame.quit()
    sys.exit(0)


if __name__ == "__main__":
    main()
