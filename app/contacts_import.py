"""Recipient list import parsing."""
import csv
import io
import re

EMAIL_RE = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')

# Header names that identify each column, lowercased and stripped.
EMAIL_HEADERS = ('email', 'e-mail', 'email address', 'mail', 'address')
NAME_HEADERS = ('name', 'full name', 'display name', 'first name', 'contact')

# A pasted list has no business being unbounded; this is a sanity bound, not a
# product limit, and the route enforces its own upload size cap as well.
MAX_ROWS = 50000

ANGLE_RE = re.compile(r'^\s*(?P<name>[^<]*?)\s*<(?P<email>[^>]+)>\s*$')

def normalize_email(value):
    value = (value or '').strip()
    match = ANGLE_RE.match(value)
    if match:
        value = match.group('email')
    return value.strip().strip('"').strip("'").lower()

def is_email(value):
    return bool(EMAIL_RE.match(value or ''))

def _split_name(value):
    match = ANGLE_RE.match((value or '').strip())
    return (match.group('name') or '').strip().strip('"') if match else ''

def _sniff_columns(header_row):
    if not header_row:
        return None
    cells = [(c or '').strip().lower() for c in header_row]
    if any(is_email(normalize_email(c)) for c in cells):
        return None
    email_idx = next((i for i, c in enumerate(cells) if c in EMAIL_HEADERS), None)
    if email_idx is None:
        return None
    name_idx = next((i for i, c in enumerate(cells) if c in NAME_HEADERS), None)
    return email_idx, name_idx

def _rows_from_text(text):
    text = (text or '').replace('\r\n', '\n').replace('\r', '\n')
    normalized = '\n'.join(
        line.replace('\t', ',').replace(';', ',') for line in text.split('\n')
    )
    return [row for row in csv.reader(io.StringIO(normalized)) if any((c or '').strip() for c in row)]

def parse_contacts(text, existing=(), suppressed=()):
    existing_set = {normalize_email(e) for e in (existing or ()) if e}
    suppressed_set = {normalize_email(e) for e in (suppressed or ()) if e}

    rows = _rows_from_text(text)[:MAX_ROWS]
    if not rows:
        return {'contacts': [], 'duplicate': [], 'suppressed': [], 'invalid': []}

    email_idx, name_idx = 0, None
    start = 0
    sniffed = _sniff_columns(rows[0])
    if sniffed:
        email_idx, name_idx = sniffed
        start = 1

    contacts, duplicate, suppressed_hits, invalid = [], [], [], []
    seen = set()

    for offset, row in enumerate(rows[start:]):
        line_no = start + offset + 1
        raw = row[email_idx] if email_idx < len(row) else ''
        email = normalize_email(raw)
        found_idx = email_idx
        if not is_email(email):
            email, found_idx = '', None
            for i, cell in enumerate(row):
                if is_email(normalize_email(cell)):
                    email, found_idx, raw = normalize_email(cell), i, cell
                    break
        if not is_email(email):
            invalid.append((line_no, ', '.join(c for c in row if c).strip()))
            continue

        if name_idx is not None and name_idx < len(row):
            name = (row[name_idx] or '').strip()
        else:
            name = _split_name(raw)
            if not name:
                # the other populated cell, when there is exactly one and it is
                # not itself an address
                others = [(c or '').strip() for i, c in enumerate(row)
                          if i != found_idx and (c or '').strip() and not is_email(normalize_email(c))]
                name = others[0] if len(others) == 1 else ''

        if email in suppressed_set:
            suppressed_hits.append(email)
            continue
        if email in existing_set or email in seen:
            duplicate.append(email)
            continue

        seen.add(email)
        contacts.append((email, name))

    return {
        'contacts': contacts,
        'duplicate': duplicate,
        'suppressed': suppressed_hits,
        'invalid': invalid,
    }

def match_contacts_to_users(contacts, users, existing=None):
    existing = existing or {}
    by_name = {}
    for user in users or []:
        name = (user.get('username') or user.get('friendly_name') or '').strip().lower()
        user_id = str(user.get('user_id') or '')
        if not name or not user_id:
            continue
        # a name held by two accounts cannot be resolved, so drop it entirely
        by_name[name] = None if name in by_name else user_id

    linked, claimed = {}, set()
    for email, name in contacts or []:
        key = (name or '').strip().lower()
        if not key:
            continue
        user_id = by_name.get(key)
        if not user_id or user_id in existing or user_id in claimed:
            continue
        if user_id in linked:
            # two contacts claiming the same account: ambiguous, so neither wins
            linked.pop(user_id)
            claimed.add(user_id)
            continue
        linked[user_id] = email
    return linked

def contacts_to_csv(contacts):
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(['email', 'name'])
    for contact in contacts or []:
        writer.writerow([contact.get('email', ''), contact.get('name', '')])
    return out.getvalue()
