"""one decision for whether a send fans out per recipient."""
import json

from app.emails.send import (
    NO_PERSONAL_DATA,
    REASON_HOSTED,
    REASON_PERSONALIZED_SECTIONS,
    REASON_TO_MODE,
    per_recipient_reasons,
)

RECS_ITEM = {'id': 'r', 'type': 'recommendations', 'userKey': '42'}
WRAPPED_ITEM = {'id': 'w', 'type': 'droppedneedle_wrapped', 'userKey': '42'}
PLAIN_ITEM = {'id': 't', 'type': 'textblock', 'content': 'hi'}
USER_DICT = {'42': 'ada@example.com'}


# --- each trigger, alone

def test_no_trigger_means_one_bcc_send():
    assert per_recipient_reasons([PLAIN_ITEM], {'send_mode': 'bcc'}, USER_DICT) == set()
    assert per_recipient_reasons([], {}, None) == set()


def test_personalized_sections_trigger():
    assert per_recipient_reasons([RECS_ITEM], {}, USER_DICT) == {REASON_PERSONALIZED_SECTIONS}
    assert per_recipient_reasons([WRAPPED_ITEM], {}, USER_DICT) == {REASON_PERSONALIZED_SECTIONS}


def test_personalized_sections_need_a_user_to_address():
    """Matches the existing route guard: recs with no user_dict cannot be split
    per user, so it stays a single send."""
    assert per_recipient_reasons([RECS_ITEM], {}, None) == set()
    assert per_recipient_reasons([RECS_ITEM], {}, {}) == set()


def test_a_section_without_a_userkey_does_not_trigger():
    assert per_recipient_reasons([{'type': 'recommendations'}], {}, USER_DICT) == set()


def test_to_mode_trigger():
    assert per_recipient_reasons([], {'send_mode': 'to'}, None) == {REASON_TO_MODE}
    assert per_recipient_reasons([], {'send_mode': 'bcc'}, None) == set()
    # blank/missing means bcc, the documented default
    assert per_recipient_reasons([], {'send_mode': ''}, None) == set()


def test_hosted_trigger():
    hosted = {'hosted_enabled': 'enabled', 'hosted_base_url': 'https://n.example.com'}
    assert per_recipient_reasons([], hosted, None) == {REASON_HOSTED}
    # enabled without a URL cannot mint unsubscribe links, so it is not a reason
    assert per_recipient_reasons([], {'hosted_enabled': 'enabled', 'hosted_base_url': '  '}, None) == set()
    assert per_recipient_reasons([], {'hosted_enabled': 'disabled', 'hosted_base_url': 'https://x'}, None) == set()


def test_triggers_accumulate():
    reasons = per_recipient_reasons(
        [RECS_ITEM],
        {'send_mode': 'to', 'hosted_enabled': 'enabled', 'hosted_base_url': 'https://n.example.com'},
        USER_DICT,
    )
    assert reasons == {REASON_PERSONALIZED_SECTIONS, REASON_TO_MODE, REASON_HOSTED}


def test_reasons_are_reported_not_just_a_boolean():
    """The point of a set: the log can say why a send produced N transactions."""
    reasons = per_recipient_reasons([], {'send_mode': 'to'}, None)
    assert isinstance(reasons, set) and REASON_TO_MODE in reasons


# --- the sentinel, which is the safety of decision 1

def test_sentinel_is_truthy_and_matches_no_real_key():
    """assemble renders EVERY user's sections when target_user_key is falsy, so
    a falsy sentinel would mail one recipient the whole list's personal data."""
    assert NO_PERSONAL_DATA
    assert NO_PERSONAL_DATA not in USER_DICT
    assert str(NO_PERSONAL_DATA) != '42'


def _render_for(target_user_key):
    from email.mime.multipart import MIMEMultipart
    from app.emails.assemble import build_email_html_with_all_cids

    # the shape the recommendations builder actually consumes
    recs = {
        '42': {'movie_posters': [{'title': 'AdaOnlyMovie', 'year': 2026, 'url': '', 'overview': ''}]},
        '99': {'movie_posters': [{'title': 'GraceOnlyMovie', 'year': 2026, 'url': '', 'overview': ''}]},
    }
    items = [
        {'id': 'r1', 'type': 'recommendations', 'userKey': '42'},
        {'id': 'r2', 'type': 'recommendations', 'userKey': '99'},
        {'id': 't', 'type': 'textblock', 'content': 'Shared for everyone'},
    ]
    html, _ = build_email_html_with_all_cids(
        {'selected_items': json.dumps(items), 'email_text': '', 'subject': 'S'},
        {'settings': {'server_name': 'Test'}}, MIMEMultipart('related'), 'email', None,
        recommendations_data=recs,
        user_dict={'42': 'ada@example.com', '99': 'grace@example.com'},
        target_user_key=target_user_key,
    )
    return html


def test_each_user_sees_only_their_own_recommendations():
    ada = _render_for('42')
    assert 'AdaOnlyMovie' in ada
    assert 'GraceOnlyMovie' not in ada

    grace = _render_for('99')
    assert 'GraceOnlyMovie' in grace
    assert 'AdaOnlyMovie' not in grace


def test_a_recipient_with_no_data_gets_shared_content_and_nobody_elses():
    """Decision 1 and the cross-contamination guarantee in one: this recipient
    used to be dropped from the send; now they receive it, and it must contain
    no other user's recommendations."""
    shared = _render_for(NO_PERSONAL_DATA)
    assert 'Shared for everyone' in shared
    assert 'AdaOnlyMovie' not in shared
    assert 'GraceOnlyMovie' not in shared


def test_passing_none_would_have_leaked_everyone():
    """Pins why the sentinel exists. A falsy target renders every user's
    sections, which is correct for a single BCC send and catastrophic for a
    per-recipient one, so the loop must never pass None."""
    everyone = _render_for(None)
    assert 'AdaOnlyMovie' in everyone and 'GraceOnlyMovie' in everyone


# --- the per-recipient loop with no unsubscribe placeholder

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


def test_loop_works_without_an_unsubscribe_placeholder():
    """`to` mode with hosted off now reaches this loop, where it previously had
    its own copy. A None placeholder used to be impossible here and would raise
    on the substitution."""
    from app.emails.send import send_personalized_per_recipient

    server = _FakeServer()
    send_personalized_per_recipient(
        server, _msg_root(), 'from@example.com',
        ['a@example.com', 'b@example.com'], '<p>body</p>', 'body',
        None, '', 'to',
    )
    assert [to for _f, to, _c in server.sent] == [('a@example.com',), ('b@example.com',)]
    # no dangling unsubscribe header when there is no endpoint to point at
    assert 'List-Unsubscribe' not in server.sent[0][2]


def test_to_mode_still_rewrites_the_to_header_per_recipient():
    from app.emails.send import send_personalized_per_recipient

    server = _FakeServer()
    send_personalized_per_recipient(
        server, _msg_root(), 'from@example.com',
        ['a@example.com', 'b@example.com'], '<p>body</p>', 'body',
        None, '', 'to',
    )
    assert 'To: a@example.com' in server.sent[0][2]
    assert 'To: b@example.com' in server.sent[1][2]


def test_placeholder_resolves_per_recipient_when_hosted_is_on():
    from app.emails.send import send_personalized_per_recipient

    server = _FakeServer()
    send_personalized_per_recipient(
        server, _msg_root(), 'from@example.com',
        ['a@example.com', 'b@example.com'],
        '<p>unsub __PH__</p>', 'unsub __PH__',
        '__PH__', 'https://n.example.com', 'bcc',
    )
    first, second = server.sent[0][2], server.sent[1][2]
    assert '__PH__' not in first and '__PH__' not in second
    assert 'List-Unsubscribe' in first
    # different recipients get different signed tokens
    assert first != second
