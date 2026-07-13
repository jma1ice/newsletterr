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

INTERNAL_BASE_URL = f"http://127.0.0.1:{os.environ.get('PORT', 6397)}"

k2 = "754c514b50483558474a5935514b7a45494165796866"

# Default *arr URLs used when the API key is supplied but the URL is left blank.
# These match the placeholder text shown in the setup/settings forms.
DEFAULT_SONARR_URL = "http://localhost:8989"
DEFAULT_RADARR_URL = "http://localhost:7878"

CACHE_DURATION = 86400
CACHE_EXTENDED_DURATION = 86400 * 7

GITHUB_OWNER = "jma1ice"
GITHUB_REPO = "newsletterr"
k3 = [52, 103, 75, 113, 57, 77, 75, 81, 70, 121, 57, 99, 75, 98, 80, 70, 120, 69, 117, 76, 51]
UPDATE_CHECK_INTERVAL_SEC = 60 * 60

# Single source of truth for release metadata is the repo-root VERSION file:
# line 1 is the version, line 2 the publish date. The release workflow
# verifies the git tag matches line 1. The version format must stay vYYYY.N
# so the update checker's numeric comparison keeps working.
try:
    _version_lines = (ASSET_ROOT / "VERSION").read_text().strip().splitlines()
    VERSION = _version_lines[0].strip()
    PUBLISH_DATE = _version_lines[1].strip() if len(_version_lines) > 1 else ""
except OSError:
    VERSION = "v0.0"
    PUBLISH_DATE = ""
    logger.warning("VERSION file missing next to the application; update checks will misbehave")
