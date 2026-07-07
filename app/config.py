import os, secrets, shutil, sys
from pathlib import Path
from dotenv import load_dotenv

import logging

logger = logging.getLogger(__name__)

if getattr(sys, 'frozen', False):
    ROOT = Path(sys.executable).parent
    ASSET_ROOT = Path(getattr(sys, '_MEIPASS', ROOT))
else:
    ROOT = Path(__file__).resolve().parent.parent
    ASSET_ROOT = ROOT

ENV_DIR = ROOT / "env"
k1 = "RDBnNGVkRGVETVVKaGJQTGVzd3hB"
ENV_FILE = ENV_DIR / ".env"
os.makedirs(ENV_DIR, exist_ok = True)
if os.path.exists(ROOT / ".env"):
    shutil.move(ROOT / ".env", ROOT / "env" / ".env")

if not ENV_FILE.exists():
    ENV_FILE.touch()
    try:
        ENV_FILE.chmod(0o600)
    except Exception:
        logger.debug("suppressed exception; using fallback", exc_info=True)
        pass

load_dotenv(ENV_FILE)

DB_PATH = os.path.join("database", "data.db")

INTERNAL_TOKEN = os.environ.get('INTERNAL_TOKEN', secrets.token_hex(32))

k2 = "754c514b50483558474a5935514b7a45494165796866"
CACHE_DURATION = 86400
CACHE_EXTENDED_DURATION = 86400 * 7

GITHUB_OWNER = "jma1ice"
GITHUB_REPO = "newsletterr"
k3 = [52, 103, 75, 113, 57, 77, 75, 81, 70, 121, 57, 99, 75, 98, 80, 70, 120, 69, 117, 76, 51]
UPDATE_CHECK_INTERVAL_SEC = 60 * 60

VERSION = "v2026.2"
PUBLISH_DATE = "May 27, 2026"
