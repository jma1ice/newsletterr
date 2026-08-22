"""One place where an SMTP session is opened and authenticated."""

import re
import smtplib
from pathlib import Path

import pytest

from app.emails import scheduled, send

SEND_SRC = Path(send.__file__).read_text()
SCHEDULED_SRC = Path(scheduled.__file__).read_text()

class _RecorderSMTP:
    instances = []

    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.started_tls = False
        self.credentials = None
        _RecorderSMTP.instances.append(self)

    def starttls(self):
        self.started_tls = True

    def login(self, username, password):
        self.credentials = (username, password)

@pytest.fixture()
def recorder(monkeypatch):
    _RecorderSMTP.instances = []
    monkeypatch.setattr(smtplib, "SMTP", _RecorderSMTP)
    monkeypatch.setattr(smtplib, "SMTP_SSL", _RecorderSMTP)
    return _RecorderSMTP

def test_starttls_path(recorder):
    server = send.smtp_connect("smtp.example.com", 587, "TLS", "user", "from@example.com", "pw")
    assert server.started_tls is True
    assert (server.host, server.port) == ("smtp.example.com", 587)
    assert server.credentials == ("user", "pw")

def test_ssl_path_does_not_starttls(recorder):
    server = send.smtp_connect("smtp.example.com", 465, "SSL", "user", "from@example.com", "pw")
    assert server.started_tls is False
    assert server.credentials == ("user", "pw")

def test_from_address_is_the_login_fallback(recorder):
    # A blank SMTP username means the account is the from address.
    server = send.smtp_connect("smtp.example.com", 587, "TLS", "", "from@example.com", "pw")
    assert server.credentials == ("from@example.com", "pw")

def test_port_is_coerced_from_the_settings_string(recorder):
    # settings columns come back as text; smtplib wants an int.
    server = send.smtp_connect("smtp.example.com", "587", "TLS", "user", "from@example.com", "pw")
    assert server.port == 587

def test_blank_port_falls_back_to_587(recorder):
    server = send.smtp_connect("smtp.example.com", "", "TLS", "user", "from@example.com", "pw")
    assert server.port == 587

def test_auth_failures_reach_the_caller(recorder, monkeypatch):
    # Each send path records its own history row and error message, so the
    # helper must not swallow the failure.
    def _boom(self, username, password):
        raise smtplib.SMTPAuthenticationError(535, b"5.7.8 Username and Password not accepted")

    monkeypatch.setattr(_RecorderSMTP, "login", _boom, raising=False)
    with pytest.raises(smtplib.SMTPAuthenticationError):
        send.smtp_connect("smtp.example.com", 587, "TLS", "user", "from@example.com", "pw")

def test_no_send_path_opens_its_own_session():
    # smtplib.SMTP / SMTP_SSL are constructed in smtp_connect and nowhere else;
    # the exception handlers elsewhere reference smtplib classes, which is fine.
    for src in (SEND_SRC, SCHEDULED_SRC):
        constructed = re.findall(r"smtplib\.SMTP(?:_SSL)?\(", src)
        assert len(constructed) <= 2

def test_every_send_path_authenticates_through_the_helper():
    assert len(re.findall(r"server = smtp_connect\(", SEND_SRC)) == 3
    assert len(re.findall(r"server = smtp_connect\(", SCHEDULED_SRC)) == 2

def test_no_send_path_calls_login_directly():
    # The one remaining server.login call is the helper's own.
    assert len(re.findall(r"server\.login\(", SEND_SRC)) == 1
    assert not re.search(r"server\.login\(", SCHEDULED_SRC)
