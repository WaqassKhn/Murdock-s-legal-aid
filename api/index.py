"""Vercel entrypoint. All credentials remain server-side."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
os.environ['LEGALLENS_SERVERLESS'] = 'true'
os.environ.setdefault('LEGALLENS_STORAGE_DIR', '/tmp/legallens')
os.environ.setdefault('LEGALLENS_MAX_UPLOAD_MB', '3')
os.environ.setdefault('LEGALLENS_MAX_PAGES', '30')
os.environ.setdefault('LEGALLENS_SECURE_COOKIES', 'true')

from app.main import app  # noqa: E402, F401
