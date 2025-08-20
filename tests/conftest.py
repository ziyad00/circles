import os
import sys
from pathlib import Path

# Ensure project root on path before importing app
project_root = Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Minimal env for tests
os.environ.setdefault(
    "APP_DATABASE_URL", "postgresql+asyncpg://postgres:password@127.0.0.1:5432/circles_test")
os.environ.setdefault("APP_DEBUG", "true")
