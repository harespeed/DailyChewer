# DailyChewer CLI / TUI Full Guide

This document covers the terminal experience for DailyChewer: the interactive TUI, the direct CLI commands, Docker Compose startup, and the daily-note calendar view.

## Entrypoints

Development entrypoint from the repository root:

```bash
python -m dailychewer.cli --help
python -m dailychewer.cli tui
```

Installed command entrypoints after `pip install -e .`:

```bash
dailychewer --help
dailychewer tui
dailychewer.cli
```

Docker entrypoints:

```bash
scripts/start_dailychewer.sh
scripts/start_dailychewer.sh --cli
COMPOSE_IGNORE_ORPHANS=true docker compose -f docker-compose-cli.yml run --rm cli
```

## One-Command Docker Startup

Build and start the GUI stack:

```bash
scripts/start_dailychewer.sh
```

Build and enter the CLI/TUI:

```bash
scripts/start_dailychewer.sh --cli
```

Only build images:

```bash
scripts/start_dailychewer.sh --build-only
```

Skip builds and start the GUI:

```bash
scripts/start_dailychewer.sh --no-build --gui
```

The script uses domestic mirrors by default:

- Debian: `http://mirrors.aliyun.com/debian`
- PyPI: `https://mirrors.aliyun.com/pypi/simple`
- npm: `https://registry.npmmirror.com`

## Split Compose Files

DailyChewer has two Compose files:

```bash
docker-compose-gui.yml
docker-compose-cli.yml
```

Both use the same Compose project name, `dailychewer`, so `backend` and `postgres` are shared. If the GUI stack has already started `dailychewer-backend-1`, the CLI stack reuses it instead of starting another backend.

Start GUI:

```bash
COMPOSE_IGNORE_ORPHANS=true docker compose -f docker-compose-gui.yml up -d backend frontend
```

Enter CLI/TUI:

```bash
COMPOSE_IGNORE_ORPHANS=true docker compose -f docker-compose-cli.yml run --rm cli
```

## Interactive TUI

Start the TUI:

```bash
python -m dailychewer.cli tui
```

or, after package installation:

```bash
dailychewer.cli
```

Guest menu:

```text
login
signup
doctor
quit
```

After login/signup:

```text
calendar
reports
search
doctor
logout
quit
```

Every TUI screen prints a `Next commands` panel so you can see valid next actions.

## Login And Signup

The TUI login/signup flow uses database-backed users. You need `DATABASE_URL` configured.

Typical Docker `.env` value:

```env
DATABASE_URL=postgresql+psycopg://dailychewer:dailychewer_password@postgres:5432/dailychewer
JWT_SECRET_KEY=change_this_secret_in_production
```

In TUI:

```text
dailychewer.cli: signup
Username: alice
Display name: Alice
Password: ********
Confirm password: ********
```

Then choose:

```text
calendar
```

## Calendar View

Direct CLI command:

```bash
dailychewer notes calendar --month 2026-06 --user alice
```

Development command:

```bash
python -m dailychewer.cli notes calendar --month 2026-06 --user alice
```

Docker command:

```bash
COMPOSE_IGNORE_ORPHANS=true docker compose -f docker-compose-cli.yml run --rm cli notes calendar --month 2026-06 --user alice
```

The calendar command prints a full month table in the terminal:

```text
DailyChewer CLI  notes calendar
2026-06  user:alice  active days:3  notes:5  deepest:4

Daily Notes Calendar 2026-06

Sun | Mon | Tue | Wed | Thu | Fri | Sat
    | 1   | 2   | 3 ●● | 4 ●●●● | 5 | 6
    |     |     | 1 条日志 | 2 条日志 |   |
```

Color and depth rules:

- Days without notes are grey.
- Days with notes are colored.
- More detailed notes use stronger colors.
- Detail level also appears as `●`, `●●`, `●●●`, or `●●●●`.
- Today is highlighted in cyan.
- A `Daily Note Logs` section lists dates, detail level, period, and preview text.
- A `Next commands` panel suggests follow-up commands.

The calendar reads existing notes only. It does not create, update, delete, migrate, or rewrite note data.

## Daily Note Calendar In TUI

Inside TUI after login:

```text
dailychewer.cli: calendar
Month (2026-06):
```

Press Enter to use the default current month, or type another `YYYY-MM`.

## Core CLI Commands

Show version:

```bash
dailychewer version
```

Run environment checks:

```bash
dailychewer doctor
dailychewer doctor --check-api
```

Generate a daily report template:

```bash
dailychewer template --date 2026-06-03 --format markdown --output input/2026-06-03.md
dailychewer template --date 2026-06-03 --format markdown --user alice
```

Ingest and optimize one report:

```bash
dailychewer ingest input/example.md --date 2026-06-03 --save --no-weekly --no-questions
dailychewer ingest input/example.md --date 2026-06-03 --project AI-App --tag backend --tag release --user alice --save --no-weekly --no-questions
```

List optimized reports:

```bash
dailychewer list
dailychewer list --week 2026-W23
dailychewer list --project AI-App
dailychewer list --tag backend
dailychewer list --user alice
```

Search optimized reports:

```bash
dailychewer search "错误码"
dailychewer search "错误码" --week 2026-W23
dailychewer search "错误码" --from 2026-06-01 --to 2026-06-30 --limit 10
dailychewer search "错误码" --user alice
```

Generate weekly reports:

```bash
dailychewer weekly --week 2026-W23 --format markdown --no-delete-prompt
dailychewer weekly --from 2026-06-01 --to 2026-06-07 --format docx --style formal --no-delete-prompt
dailychewer weekly --week 2026-W23 --format markdown --preview --user alice
```

Generate monthly reports:

```bash
dailychewer monthly --month 2026-06 --format markdown --style formal
dailychewer monthly --month 2026-06 --format docx --user alice
```

Clean one week of local-mode files:

```bash
dailychewer clean --week 2026-W23
```

## User Commands

Create a database user:

```bash
dailychewer user create alice --password password123 --display-name Alice
dailychewer user create admin --password admin123 --display-name Admin --admin
```

List users:

```bash
dailychewer user list
```

Disable or enable a user:

```bash
dailychewer user disable alice
dailychewer user enable alice
```

Reset a password:

```bash
dailychewer user reset-password alice --password newpass123
```

## Database Commands

Check database readiness:

```bash
dailychewer db check
```

Initialize database schema and default admin:

```bash
dailychewer db init
```

Run in Docker:

```bash
COMPOSE_IGNORE_ORPHANS=true docker compose -f docker-compose-cli.yml run --rm cli db init
```

## Backup Commands

Create a backup:

```bash
dailychewer backup create --output backups --zip
```

Verify a backup:

```bash
dailychewer backup verify backups/<backup-dir-or-zip>
```

Dry-run restore:

```bash
dailychewer backup restore backups/<backup-dir> --restore-files
```

Apply restore:

```bash
dailychewer backup restore backups/<backup-dir> --apply --restore-files
```

Database restore requires explicit confirmation:

```bash
dailychewer backup restore backups/<backup-dir> --apply --restore-db --confirm-overwrite-db
```

## Legacy Index Migration

Preview migration from legacy `data/index.json` into one database user scope:

```bash
dailychewer migrate-index --user alice
```

Apply migration:

```bash
dailychewer migrate-index --user alice --apply
```

Copy legacy files into user storage during migration:

```bash
dailychewer migrate-index --user alice --apply --copy-files
```

## Local Mode vs Database User Mode

Local mode:

```bash
dailychewer list
dailychewer search "keyword"
dailychewer ingest input/example.md --save
```

Database user mode:

```bash
dailychewer list --user alice
dailychewer search "keyword" --user alice
dailychewer ingest input/example.md --save --user alice
dailychewer notes calendar --month 2026-06 --user alice
```

The note calendar requires database user mode because notes are stored per user in PostgreSQL.

## Troubleshooting

Check Docker services:

```bash
docker compose -f docker-compose-gui.yml ps
docker compose -f docker-compose-cli.yml ps
```

Check backend health:

```bash
curl http://localhost:8000/api/health
```

Check GUI:

```bash
open http://localhost:5173
```

If Compose prints orphan warnings, use:

```bash
COMPOSE_IGNORE_ORPHANS=true
```

If domestic mirrors are slow, override them:

```bash
APT_MIRROR=http://mirrors.aliyun.com/debian \
PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple \
PIP_TRUSTED_HOST=mirrors.aliyun.com \
NPM_CONFIG_REGISTRY=https://registry.npmmirror.com \
scripts/start_dailychewer.sh --build-only
```

If `dailychewer.cli` is not found locally, install the project:

```bash
pip install -e .
```
