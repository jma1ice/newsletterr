import sqlite3

from app import config
from app.store import record_email_history, EMAIL_HISTORY_RETENTION

def _count(status=None):
    conn = sqlite3.connect(config.DB_PATH)
    if status:
        n = conn.execute("SELECT COUNT(*) FROM email_history WHERE status = ?", (status,)).fetchone()[0]
    else:
        n = conn.execute("SELECT COUNT(*) FROM email_history").fetchone()[0]
    conn.close()
    return n

def test_record_success_and_failure(app):
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute("DELETE FROM email_history")
    conn.commit()
    conn.close()

    record_email_history("Sent one", "a@b.c", "<html>", 1.2, 1, "Manual")
    record_email_history("Failed one", "d@e.f", "", 0, 1, "Manual", status="failed", error="SMTP auth failed")

    conn = sqlite3.connect(config.DB_PATH)
    rows = conn.execute("SELECT subject, status, error FROM email_history ORDER BY id").fetchall()
    conn.close()
    assert ("Sent one", "sent", None) in rows
    assert ("Failed one", "failed", "SMTP auth failed") in rows

def test_history_retention_prunes_old_rows(app):
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute("DELETE FROM email_history")
    conn.commit()
    conn.close()

    for i in range(EMAIL_HISTORY_RETENTION + 25):
        record_email_history(f"msg {i}", "a@b.c", "", 0, 1, "Manual")

    assert _count() == EMAIL_HISTORY_RETENTION  # capped

def test_recipients_string_is_capped(app):
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute("DELETE FROM email_history")
    conn.commit()
    conn.close()
    record_email_history("big", "x@y.z, " * 2000, "", 0, 2000, "Manual")
    conn = sqlite3.connect(config.DB_PATH)
    stored = conn.execute("SELECT recipients FROM email_history ORDER BY id DESC LIMIT 1").fetchone()[0]
    conn.close()
    assert len(stored) <= 5000

def test_email_history_page_renders_with_status(client, seeded_settings):
    record_email_history("Failed send", "a@b.c", "", 0, 1, "Manual", status="failed", error="boom")
    html = client.get("/email_history").get_data(as_text=True)
    assert "Failed" in html and "boom" in html
