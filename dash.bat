@echo off
REM ButterClaw Operator Launcher — Strictly executes inside the Docker container
REM Usage:
REM   dash.bat                                -> Launch live TUI dashboard
REM   dash.bat skills                         -> List attested SKILL.md packages
REM   dash.bat audit /data/skills/<skill_dir> -> Audit & Merkle-lock a skill in container
REM   dash.bat test                           -> Run SkillGuard test suite in container

if /I "%~1"=="skills" (
    docker compose exec -it butterclaw python -m butterclaw.setup_wizard --list-skills
    goto :eof
)

if /I "%~1"=="audit" (
    if "%~2"=="" (
        echo Usage: dash.bat audit /data/skills/^<skill-folder^>
        exit /b 1
    )
    docker compose exec -it butterclaw python -m butterclaw.setup_wizard --audit-skill "%~2"
    goto :eof
)

if /I "%~1"=="test" (
    docker compose exec -it butterclaw python tests/test_skill_guard.py
    goto :eof
)

docker compose exec -it butterclaw python -m butterclaw.tui_dashboard %*