#!/bin/bash
# ButterClaw Operator Launcher — Strictly executes inside the Docker container
set -e

case "${1:-}" in
    skills|--list-skills)
        docker compose exec -it butterclaw python -m butterclaw.setup_wizard --list-skills
        ;;
    audit|--audit-skill)
        if [ -z "${2:-}" ]; then
            echo "Usage: ./dash.sh audit /data/skills/<skill-folder>"
            exit 1
        fi
        docker compose exec -it butterclaw python -m butterclaw.setup_wizard --audit-skill "$2"
        ;;
    test)
        docker compose exec -it butterclaw python tests/test_skill_guard.py
        ;;
    *)
        docker compose exec -it butterclaw python -m butterclaw.tui_dashboard "$@"
        ;;
esac