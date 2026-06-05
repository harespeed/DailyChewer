from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
for extra_path in (PROJECT_ROOT / "backend", PROJECT_ROOT / "cli"):
    if str(extra_path) not in sys.path:
        sys.path.insert(0, str(extra_path))
