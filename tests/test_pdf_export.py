# PDF export (NEWS-9): both routes return a valid PDF for small fixtures.
# No pixel assertions; weasyprint's own rendering is trusted.

import sqlite3

import pytest

@pytest.fixture()
def pdf_env(app, client):
    from app import config

    conn = sqlite3.connect(config.DB_PATH)
    conn.execute("INSERT OR IGNORE INTO settings (id) VALUES (1)")
    conn.execute("UPDATE settings SET server_name='TestPlex', from_email='news@example.com' WHERE id = 1")
    conn.commit()
    conn.close()

    with client.session_transaction() as sess:
        sess["csrf_token"] = "pdf-token"
    return client

def test_export_pdf_returns_valid_pdf(pdf_env):
    resp = pdf_env.post("/export_pdf", json={
        "subject": "PDF Test", "email_header_title": "The Header",
        "selected_items": [{"type": "textblock", "content": "PDF body text"}],
        "custom_html": "", "expanded_collections": {},
    }, headers={"X-CSRF-Token": "pdf-token"})
    assert resp.status_code == 200
    assert resp.mimetype == "application/pdf"
    assert resp.data.startswith(b"%PDF")
    assert "pdf-test.pdf" in resp.headers.get("Content-Disposition", "")

def test_export_pdf_custom_html_with_token(pdf_env):
    resp = pdf_env.post("/export_pdf", json={
        "subject": "Custom PDF", "email_header_title": "",
        "selected_items": [],
        "custom_html": "<html><body><h1>Custom</h1>{{snapin:wrapped}}</body></html>",
        "expanded_collections": {},
    }, headers={"X-CSRF-Token": "pdf-token"})
    assert resp.status_code == 200
    assert resp.data.startswith(b"%PDF")

def test_history_pdf_extracts_html_and_resolves_cids(pdf_env):
    from app import config
    from app.store import record_email_history

    # 1x1 transparent PNG
    png_b64 = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGBg"
        "AAAABQABh6FO1AAAAABJRU5ErkJggg=="
    )
    stored_mime = (
        "Subject: Stored Email\r\n"
        "From: news@example.com\r\n"
        "To: a@b.c\r\n"
        "MIME-Version: 1.0\r\n"
        'Content-Type: multipart/related; boundary="BOUND"\r\n'
        "\r\n"
        "--BOUND\r\n"
        "Content-Type: text/html; charset=utf-8\r\n"
        "\r\n"
        '<html><body><p>Stored body</p><img src="cid:img1" alt="x"></body></html>\r\n'
        "--BOUND\r\n"
        "Content-Type: image/png\r\n"
        "Content-ID: <img1>\r\n"
        "Content-Transfer-Encoding: base64\r\n"
        "\r\n"
        f"{png_b64}\r\n"
        "--BOUND--\r\n"
    )
    record_email_history("Stored Email", "a@b.c", stored_mime, 1.0, 1, "Manual")

    conn = sqlite3.connect(config.DB_PATH)
    history_id = conn.execute("SELECT id FROM email_history ORDER BY id DESC LIMIT 1").fetchone()[0]
    conn.close()

    resp = pdf_env.get(f"/email_history/{history_id}/pdf")
    assert resp.status_code == 200
    assert resp.mimetype == "application/pdf"
    assert resp.data.startswith(b"%PDF")
    assert "stored-email.pdf" in resp.headers.get("Content-Disposition", "")

def test_history_pdf_missing_row_404(pdf_env):
    resp = pdf_env.get("/email_history/999999/pdf")
    assert resp.status_code == 404

def test_history_pdf_cid_rewrite_unit():
    # the cid: -> data URI rewrite itself, without rendering
    from app.emails import pdf as pdf_mod

    captured = {}
    def _fake_render(html):
        captured["html"] = html
        return b"%PDF-fake"

    import email as email_lib  # noqa: F401 (documents the shape under test)
    stored = (
        "Subject: X\r\n"
        'Content-Type: multipart/related; boundary="B"\r\n'
        "\r\n"
        "--B\r\n"
        "Content-Type: text/html\r\n"
        "\r\n"
        '<img src="cid:pic">\r\n'
        "--B\r\n"
        "Content-Type: image/png\r\n"
        "Content-ID: <pic>\r\n"
        "Content-Transfer-Encoding: base64\r\n"
        "\r\n"
        "aGk=\r\n"
        "--B--\r\n"
    )
    orig = pdf_mod.render_html_to_pdf
    pdf_mod.render_html_to_pdf = _fake_render
    try:
        out = pdf_mod.render_history_email_to_pdf(stored)
    finally:
        pdf_mod.render_html_to_pdf = orig
    assert out == b"%PDF-fake"
    assert "cid:pic" not in captured["html"]
    assert "data:image/png;base64,aGk=" in captured["html"]
