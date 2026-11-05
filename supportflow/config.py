"""Project paths and immutable demo-wide settings."""
from __future__ import annotations
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / '.env', override=False)
except ImportError:
    pass  # Core Stage 2 operation remains possible without the Stage 3 AI extras.
raw_db = Path(os.getenv('SUPPORTFLOW_DB_PATH', 'data/supportflow.db'))
DB_PATH = raw_db if raw_db.is_absolute() else ROOT / raw_db
UPLOAD_DIR = ROOT / 'data' / 'uploads'
MAX_IMAGE_BYTES = 5 * 1024 * 1024
CATEGORIES = ['Delivery', 'Refund', 'Product quality', 'Billing', 'Account', 'Other']
ROLE_NAMES = {'customer':'Customer', 'agent':'Support agent', 'approver':'Approver', 'admin':'Administrator'}
APP_TIMEZONE = 'Asia/Bangkok'
