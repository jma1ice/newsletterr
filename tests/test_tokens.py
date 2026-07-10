from itsdangerous import URLSafeSerializer

from app.crypto import ensure_secret_key
from app.tokens import make_unsubscribe_placeholder, sign_unsubscribe_token, verify_unsubscribe_token

def test_round_trip():
    token = sign_unsubscribe_token("user@example.com")
    assert verify_unsubscribe_token(token) == "user@example.com"

def test_normalizes_case_and_whitespace():
    token = sign_unsubscribe_token("  User@Example.COM  ")
    assert verify_unsubscribe_token(token) == "user@example.com"

def test_tampered_token_rejected():
    token = sign_unsubscribe_token("user@example.com")
    # flip a character in the middle (payload portion) rather than the very
    # last char, base64 padding bits can make single-trailing-char flips
    # decode to an identical byte, giving false negatives on this check
    mid = len(token) // 2
    flipped = "a" if token[mid] != "a" else "b"
    tampered = token[:mid] + flipped + token[mid + 1:]
    assert verify_unsubscribe_token(tampered) is None

def test_garbage_token_rejected():
    assert verify_unsubscribe_token("not-a-real-token") is None
    assert verify_unsubscribe_token("") is None

def test_different_salt_cannot_cross_verify():
    # simulates another token type (e.g. a future hosted-page or CSRF-like
    # token) sharing the same underlying secret key but a different salt,
    # must not be replayable as an unsubscribe token, and vice versa.
    other_serializer = URLSafeSerializer(ensure_secret_key(), salt="something-else")
    foreign_token = other_serializer.dumps("user@example.com")
    assert verify_unsubscribe_token(foreign_token) is None

def test_placeholder_is_unique_and_not_html_special():
    a = make_unsubscribe_placeholder()
    b = make_unsubscribe_placeholder()
    assert a != b
    assert a.startswith("__UNSUB_TOKEN_") and a.endswith("__")
    for ch in a:
        assert ch.isalnum() or ch == "_"
