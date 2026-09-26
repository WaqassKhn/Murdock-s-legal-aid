"""Vercel entrypoint. All credentials remain server-side."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
os.environ['LEGALLENS_TEMPORARY_SESSION'] = 'true'

from app.temporary_session import create_session_app  # noqa: E402

app = create_session_app()
