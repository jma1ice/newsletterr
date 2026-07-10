import secrets

from itsdangerous import URLSafeSerializer, BadSignature

from app.crypto import ensure_secret_key

# Distinct salt keeps this cryptographically separate from Flask's session
# cookie signing even though both derive from NEWSLETTERR_SECRET_KEY.
_serializer = URLSafeSerializer(ensure_secret_key(), salt="unsubscribe")

def sign_unsubscribe_token(email: str) -> str:
    return _serializer.dumps((email or "").strip().lower())

def verify_unsubscribe_token(token: str) -> str | None:
    try:
        return _serializer.loads(token)
    except BadSignature:
        return None

def make_unsubscribe_placeholder() -> str:
    """A per-send sentinel embedded in the rendered HTML/plain-text body,
    swapped for each recipient's real signed token right before that
    recipient's SMTP transaction (see send.py/scheduled.py)."""
    return f"__UNSUB_TOKEN_{secrets.token_hex(12)}__"
