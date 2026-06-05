"""Backend package namespace for DailyChewer."""

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
CLI_ROOT = PROJECT_ROOT / "cli"

for extra_path in (BACKEND_ROOT, CLI_ROOT):
    if str(extra_path) not in sys.path:
        sys.path.insert(0, str(extra_path))
