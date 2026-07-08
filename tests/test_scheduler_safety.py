import sqlite3
from datetime import datetime, timedelta

from app import config
from app.store import advance_schedule_next_send

def _make_due_schedule(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute("INSERT OR IGNORE INTO email_lists (id, name, emails) VALUES (500, 'l', 'a@b.c')")
    conn.execute("INSERT OR IGNORE INTO email_templates (id, name, selected_items) VALUES (500, 't', '[]')")
    past = (datetime.now() - timedelta(days=1)).isoformat()
    conn.execute(
        "INSERT OR REPLACE INTO email_schedules "
        "(id, name, email_list_id, template_id, frequency, start_date, send_time, next_send, is_active) "
        "VALUES (500, 's', 500, 500, 'daily', ?, '09:00', ?, 1)",
        (past, past),
    )
    conn.commit()
    conn.close()

def test_advance_moves_next_send_future_without_touching_last_sent(app):
    _make_due_schedule(config.DB_PATH)

    conn = sqlite3.connect(config.DB_PATH)
    before = conn.execute("SELECT next_send, last_sent FROM email_schedules WHERE id = 500").fetchone()
    conn.close()
    assert datetime.fromisoformat(before[0]) <= datetime.now()  # was due

    advance_schedule_next_send(500)

    conn = sqlite3.connect(config.DB_PATH)
    after = conn.execute("SELECT next_send, last_sent FROM email_schedules WHERE id = 500").fetchone()
    conn.close()
    # next_send is now in the future -> a crash mid-send cannot re-blast next tick
    assert datetime.fromisoformat(after[0]) > datetime.now()
    # last_sent untouched (only a successful send records that)
    assert after[1] == before[1]
