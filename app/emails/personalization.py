"""Per-recipient personalization tokens."""
import re

from app.security import escape_html_output as esc

TOKEN_RE = re.compile(r'\{\{\s*(name|email|first_name)\s*\}\}', re.IGNORECASE)

DEFAULT_NAME = 'there'

def has_tokens(*texts):
    return any(TOKEN_RE.search(text or '') for text in texts)

def _first_name(name):
    return (name or '').strip().split(' ')[0]

def resolve(text, email, name=None, escape=True):
    if not text:
        return text

    name = (name or '').strip()
    values = {
        'name': name or DEFAULT_NAME,
        'first_name': _first_name(name) or DEFAULT_NAME,
        'email': (email or '').strip(),
    }

    def _sub(match):
        value = values.get(match.group(1).lower(), '')
        return esc(value) if escape else value

    return TOKEN_RE.sub(_sub, text)

def resolve_pair(html, plain, email, name=None):
    return (
        resolve(html, email, name, escape=True),
        resolve(plain, email, name, escape=False),
    )
