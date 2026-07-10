import sqlite3

from app import config
from app.store import record_email_history, EMAIL_HISTORY_RETENTION, RECIPIENTS_MAX_CHARS, EMAIL_CONTENT_MAX_CHARS

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
    oversized_recipient_count = (RECIPIENTS_MAX_CHARS // 7) + 100
    record_email_history("big", "x@y.z, " * oversized_recipient_count, "", 0, oversized_recipient_count, "Manual")
    conn = sqlite3.connect(config.DB_PATH)
    stored = conn.execute("SELECT recipients FROM email_history ORDER BY id DESC LIMIT 1").fetchone()[0]
    conn.close()
    assert len(stored) <= RECIPIENTS_MAX_CHARS

def test_email_content_stores_full_mime_for_resend(app):
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute("DELETE FROM email_history")
    conn.commit()
    conn.close()
    # a realistic full send stores far more than the old 1000-char preview cap
    full_mime = "<html>" + ("x" * 50_000) + "</html>"
    record_email_history("full body", "a@b.c", full_mime, 50, 1, "Manual")
    conn = sqlite3.connect(config.DB_PATH)
    stored = conn.execute("SELECT email_content FROM email_history ORDER BY id DESC LIMIT 1").fetchone()[0]
    conn.close()
    assert stored == full_mime
    assert len(stored) > 1000

def test_email_content_is_capped_at_sanity_ceiling(app):
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute("DELETE FROM email_history")
    conn.commit()
    conn.close()
    oversized = "x" * (EMAIL_CONTENT_MAX_CHARS + 1000)
    record_email_history("oversized", "a@b.c", oversized, 5000, 1, "Manual")
    conn = sqlite3.connect(config.DB_PATH)
    stored = conn.execute("SELECT email_content FROM email_history ORDER BY id DESC LIMIT 1").fetchone()[0]
    conn.close()
    assert len(stored) <= EMAIL_CONTENT_MAX_CHARS

def test_email_history_page_renders_with_status(client, seeded_settings):
    record_email_history("Failed send", "a@b.c", "", 0, 1, "Manual", status="failed", error="boom")
    html = client.get("/email_history").get_data(as_text=True)
    assert "Failed" in html and "boom" in html
