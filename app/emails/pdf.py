# PDF export (NEWS-9). weasyprint (pure Python, no browser) renders the same
# HTML the preview pipeline produces. A custom url_fetcher resolves internal
# URLs (poster proxy, static assets) against INTERNAL_BASE_URL with the
# X-Internal-Token header, exactly how email image fetching resolves them;
# external URLs go through the SSRF-guarded safe_get. Renders are
# request-scoped with no shared state, so gthread concurrency is safe.
#
# Known limits: email-safe table layouts render well; linear-gradient (the
# wrapped card) is supported; client-specific hacks (mso comments) are
# ignored, which is fine for PDF.
import base64
import email as email_lib
import re

import requests

from app import config
from app.security import safe_get

import logging

logger = logging.getLogger(__name__)

def _fetcher_response(url, resp):
    from weasyprint.urls import URLFetcherResponse

    content_type = (resp.headers.get('Content-Type') or '').strip()
    headers = {'Content-Type': content_type} if content_type else None
    return URLFetcherResponse(url, body=resp.content, headers=headers)

def _make_url_fetcher():
    # weasyprint is imported lazily so environments without its native deps
    # (pango/cairo) only fail on use, never at app boot. A fresh instance per
    # render: URLFetcher keeps per-fetch state, so sharing one across gthread
    # requests would race.
    from weasyprint import URLFetcher

    class _NewsletterrURLFetcher(URLFetcher):
        def fetch(self, url, headers=None):
            internal_base = config.INTERNAL_BASE_URL.rstrip('/')
            if url.startswith(internal_base + '/') or url == internal_base:
                resp = requests.get(url, headers={'X-Internal-Token': config.INTERNAL_TOKEN}, timeout=15)
                resp.raise_for_status()
                return _fetcher_response(url, resp)
            if url.startswith(('http://', 'https://')):
                resp = safe_get(url, timeout=15)
                resp.raise_for_status()
                return _fetcher_response(url, resp)
            # data: URIs (cid rewrites) and other schemes use the stock fetcher
            return super().fetch(url, headers=headers)

    return _NewsletterrURLFetcher()

def render_html_to_pdf(html):
    """PDF bytes for an email HTML document. Relative URLs resolve against
    INTERNAL_BASE_URL through the token-carrying fetcher above."""
    from weasyprint import HTML

    return HTML(string=html, base_url=config.INTERNAL_BASE_URL, url_fetcher=_make_url_fetcher()).write_pdf()

def render_history_email_to_pdf(email_content):
    """PDF bytes for a stored email_history MIME message: the html part is
    extracted and its cid: references rewritten to data URIs built from the
    stored image parts, so the PDF matches what recipients saw without any
    re-fetching."""
    msg = email_lib.message_from_string(email_content)

    html = None
    plain = None
    images = {}
    for part in msg.walk():
        ctype = part.get_content_type()
        if ctype == 'text/html' and html is None:
            payload = part.get_payload(decode=True) or b''
            html = payload.decode(part.get_content_charset() or 'utf-8', 'replace')
        elif ctype == 'text/plain' and plain is None:
            payload = part.get_payload(decode=True) or b''
            plain = payload.decode(part.get_content_charset() or 'utf-8', 'replace')
        elif ctype.startswith('image/'):
            cid = (part.get('Content-ID') or '').strip('<>')
            if cid:
                data = part.get_payload(decode=True) or b''
                images[cid] = f"data:{ctype};base64,{base64.b64encode(data).decode('ascii')}"

    if html is None:
        # older/simple rows store a bare body; fall back to whatever is there
        body = msg.get_payload()
        if isinstance(body, list):
            body = plain or ''
        html = body if '<' in (body or '') else f"<pre>{body or ''}</pre>"

    for cid, data_uri in images.items():
        html = html.replace(f"cid:{cid}", data_uri)

    return render_html_to_pdf(html)

def pdf_filename(subject):
    slug = re.sub(r'[^a-z0-9]+', '-', (subject or 'newsletterr-email').lower()).strip('-')
    return f"{slug or 'newsletterr-email'}.pdf"
