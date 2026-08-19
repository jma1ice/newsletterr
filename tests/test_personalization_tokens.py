"""per-recipient personalization tokens."""
import sqlite3

from app import config
from app.emails import personalization
from app.emails.send import REASON_TOKENS, per_recipient_reasons


# --- detection

def test_detects_each_supported_token():
    for token in ('{{name}}', '{{email}}', '{{first_name}}'):
        assert personalization.has_tokens(f"Hi {token},")


def test_detection_tolerates_spacing_and_case():
    assert personalization.has_tokens("Hi {{ name }},")
    assert personalization.has_tokens("Hi {{NAME}},")
    assert personalization.has_tokens("Hi {{ Name }},")


def test_unknown_braces_are_not_personalization():
    """A narrow allowlist, not arbitrary attribute access."""
    for text in ("{{ссылка}}", "{{admin_password}}", "{{ }}", "{{}}", "{ name }", "plain text"):
        assert not personalization.has_tokens(text)


def test_snapin_tokens_are_a_different_mechanism():
    """Shared braces, opposite substitution point. A snap-in token must not
    make a send fan out per recipient."""
    assert not personalization.has_tokens("{{snapin:recently_added}}")
    assert not personalization.has_tokens("{{snapin:wrapped}}")


def test_has_tokens_handles_none_and_empty():
    assert not personalization.has_tokens(None)
    assert not personalization.has_tokens("", None)


# --- resolution

def test_resolves_name_and_email():
    out = personalization.resolve("Hi {{name}} <{{email}}>", "ada@example.com", "Ada Lovelace", escape=False)
    assert out == "Hi Ada Lovelace <ada@example.com>"


def test_first_name_takes_the_leading_word():
    out = personalization.resolve("Hi {{first_name}},", "a@b.co", "Ada Lovelace", escape=False)
    assert out == "Hi Ada,"


def test_missing_name_falls_back_rather_than_greeting_nobody():
    """An import does not require the name column, so this is the common case.
    "Hi ," is a worse greeting than a generic one."""
    for missing in (None, "", "   "):
        out = personalization.resolve("Hi {{name}},", "a@b.co", missing, escape=False)
        assert out == f"Hi {personalization.DEFAULT_NAME},"
        assert "Hi ," not in out


def test_email_still_resolves_without_a_name():
    out = personalization.resolve("{{email}}", "a@b.co", None, escape=False)
    assert out == "a@b.co"


# --- escaping, the security-relevant part

def test_html_escapes_the_name():
    """An import can put anything in the name column, and it lands in email
    HTML."""
    out = personalization.resolve("Hi {{name}},", "a@b.co", '<script>alert(1)</script>', escape=True)
    assert '<script>' not in out
    assert '&lt;script&gt;' in out


def test_plain_text_does_not_escape():
    """Escaping the text/plain alternative would show the reader a literal
    &amp; instead of an ampersand."""
    out = personalization.resolve("Hi {{name}},", "a@b.co", 'Ada & Grace', escape=False)
    assert out == "Hi Ada & Grace,"


def test_resolve_pair_escapes_each_part_as_it_needs():
    html, plain = personalization.resolve_pair(
        "<p>Hi {{name}}</p>", "Hi {{name}}", "a@b.co", "Ada & Grace")
    assert "Ada &amp; Grace" in html
    assert "Ada & Grace" in plain


def test_a_name_cannot_inject_another_token():
    """A name containing a token must not be re-expanded on a second pass."""
    out = personalization.resolve("Hi {{name}},", "a@b.co", "{{email}}", escape=False)
    assert out == "Hi {{email}},"


# --- the fan-out decision

def test_a_token_forces_per_recipient_sending():
    reasons = per_recipient_reasons([], {'send_mode': 'bcc'}, None, "<p>Hi {{name}}</p>", "Hi {{name}}")
    assert REASON_TOKENS in reasons


def test_no_token_leaves_a_bcc_send_alone():
    assert per_recipient_reasons([], {'send_mode': 'bcc'}, None, "<p>Hello all</p>", "Hello all") == set()


def test_a_token_in_the_plain_part_alone_still_counts():
    assert REASON_TOKENS in per_recipient_reasons([], {}, None, "<p>Hello</p>", "Hi {{name}}")


def test_token_reason_stacks_with_the_others():
    reasons = per_recipient_reasons([], {'send_mode': 'to'}, None, "Hi {{name}}", "Hi {{name}}")
    assert REASON_TOKENS in reasons and len(reasons) == 2


# --- the name lookup

def test_contact_names_are_looked_up_across_lists(app):
    from app.store import add_contacts, get_contact_names

    conn = sqlite3.connect(config.DB_PATH)
    conn.execute("INSERT OR IGNORE INTO email_lists (id, name, emails) VALUES (930, 'TokA', '')")
    conn.execute("INSERT OR IGNORE INTO email_lists (id, name, emails) VALUES (931, 'TokB', '')")
    conn.commit()
    conn.close()
    try:
        add_contacts(930, [('ada@example.com', 'Ada')])
        add_contacts(931, [('grace@example.com', 'Grace')])
        names = get_contact_names()
        # a send's recipients can span lists, so the lookup is not list scoped
        assert names['ada@example.com'] == 'Ada'
        assert names['grace@example.com'] == 'Grace'
    finally:
        conn = sqlite3.connect(config.DB_PATH)
        conn.execute("DELETE FROM contacts WHERE list_id IN (930, 931)")
        conn.execute("DELETE FROM email_lists WHERE id IN (930, 931)")
        conn.commit()
        conn.close()


def test_contacts_without_a_name_are_left_out_of_the_lookup(app):
    from app.store import add_contacts, get_contact_names

    conn = sqlite3.connect(config.DB_PATH)
    conn.execute("INSERT OR IGNORE INTO email_lists (id, name, emails) VALUES (932, 'TokC', '')")
    conn.commit()
    conn.close()
    try:
        add_contacts(932, [('noname@example.com', '')])
        assert 'noname@example.com' not in get_contact_names()
    finally:
        conn = sqlite3.connect(config.DB_PATH)
        conn.execute("DELETE FROM contacts WHERE list_id = 932")
        conn.execute("DELETE FROM email_lists WHERE id = 932")
        conn.commit()
        conn.close()


# --- end to end through the send loop

class _FakeServer:
    def __init__(self):
        self.sent = []

    def sendmail(self, from_addr, to_addrs, content):
        self.sent.append((from_addr, tuple(to_addrs), content))


def _msg_root():
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    root = MIMEMultipart('related')
    alt = MIMEMultipart('alternative')
    alt.attach(MIMEText('plain', 'plain', 'utf-8'))
    root.attach(alt)
    root['To'] = 'placeholder@example.com'
    return root


def test_each_recipient_gets_their_own_name(app):
    import base64
    from app.emails.send import send_personalized_per_recipient
    from app.store import add_contacts

    conn = sqlite3.connect(config.DB_PATH)
    conn.execute("INSERT OR IGNORE INTO email_lists (id, name, emails) VALUES (933, 'TokE2E', '')")
    conn.commit()
    conn.close()
    try:
        add_contacts(933, [('ada@example.com', 'Ada'), ('grace@example.com', 'Grace')])

        server = _FakeServer()
        send_personalized_per_recipient(
            server, _msg_root(), 'from@example.com',
            ['ada@example.com', 'grace@example.com', 'stranger@example.com'],
            '<p>Hi {{name}}</p>', 'Hi {{name}}',
            None, '', 'to',
        )
        bodies = []
        for _f, _to, content in server.sent:
            # the parts are base64 encoded in the assembled message
            decoded = content
            for chunk in content.split('\n\n'):
                try:
                    decoded += base64.b64decode(chunk).decode('utf-8', errors='ignore')
                except Exception:
                    pass
            bodies.append(decoded)

        assert 'Hi Ada' in bodies[0] and 'Hi Grace' not in bodies[0]
        assert 'Hi Grace' in bodies[1] and 'Hi Ada' not in bodies[1]
        # a recipient with no contact row gets the fallback, not someone's name
        assert f'Hi {personalization.DEFAULT_NAME}' in bodies[2]
        assert 'Hi Ada' not in bodies[2] and 'Hi Grace' not in bodies[2]
    finally:
        conn = sqlite3.connect(config.DB_PATH)
        conn.execute("DELETE FROM contacts WHERE list_id = 933")
        conn.execute("DELETE FROM email_lists WHERE id = 933")
        conn.commit()
        conn.close()


def test_no_token_means_no_contact_lookup(app, monkeypatch):
    """A send with no tokens must not pay for the query."""
    from app.emails import send as send_mod

    monkeypatch.setattr(send_mod, 'get_contact_names',
                        lambda: (_ for _ in ()).throw(AssertionError("looked up names with no tokens")))
    server = _FakeServer()
    send_mod.send_personalized_per_recipient(
        server, _msg_root(), 'from@example.com', ['a@example.com'],
        '<p>No tokens here</p>', 'No tokens here', None, '', 'to',
    )
    assert len(server.sent) == 1
