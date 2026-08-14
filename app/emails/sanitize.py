"""HTML allowlist for rich text blocks.

Three rules:

* tags not on the allowlist are unwrapped, keeping their text, except for the
  few whose content is itself dangerous - those are dropped whole;
* attributes are allowlisted globally, with url attributes scheme-checked and
  `style` filtered property by property;
* anything that could execute (on* handlers, javascript: urls) never survives,
  whatever casing or whitespace it is written in.
"""
from html.parser import HTMLParser
from html import escape

import logging

logger = logging.getLogger(__name__)

# Formatting and simple structure. Deliberately includes the block and list
# tags an editor emits, and table tags because email authors do use them.
ALLOWED_TAGS = frozenset({
    'a', 'b', 'strong', 'i', 'em', 'u', 's', 'strike', 'del', 'ins', 'mark',
    'span', 'div', 'p', 'br', 'hr', 'small', 'sub', 'sup', 'code', 'pre',
    'blockquote', 'ul', 'ol', 'li', 'dl', 'dt', 'dd',
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'table', 'thead', 'tbody', 'tfoot', 'tr', 'td', 'th', 'caption',
    'img', 'figure', 'figcaption', 'font', 'center',
})

# Tags whose *contents* must go with them: unwrapping a <script> would leave
# its source as visible text, and worse, could re-form markup downstream.
DROP_WITH_CONTENT = frozenset({
    'script', 'style', 'iframe', 'object', 'embed', 'applet', 'noscript',
    'template', 'svg', 'math', 'form', 'input', 'button', 'select', 'textarea',
    'link', 'meta', 'base', 'title', 'head',
})

VOID_TAGS = frozenset({'br', 'hr', 'img'})

ALLOWED_ATTRS = frozenset({
    'href', 'src', 'alt', 'title', 'width', 'height', 'align', 'valign',
    'style', 'target', 'rel', 'colspan', 'rowspan', 'border', 'cellpadding',
    'cellspacing', 'bgcolor', 'color', 'face', 'size', 'dir', 'lang',
})

URL_ATTRS = frozenset({'href', 'src'})
SAFE_SCHEMES = ('http://', 'https://', 'mailto:', 'cid:', 'tel:')

# Inline style properties an email can actually use. Anything else (position,
# behavior, expression, url(...) backgrounds) is dropped.
ALLOWED_STYLE_PROPS = frozenset({
    'color', 'background-color', 'font-size', 'font-family', 'font-weight',
    'font-style', 'text-align', 'text-decoration', 'text-transform',
    'line-height', 'letter-spacing', 'margin', 'margin-top', 'margin-bottom',
    'margin-left', 'margin-right', 'padding', 'padding-top', 'padding-bottom',
    'padding-left', 'padding-right', 'border', 'border-top', 'border-bottom',
    'border-left', 'border-right', 'border-radius', 'border-color',
    'width', 'max-width', 'height', 'display', 'vertical-align',
    'white-space', 'font', 'list-style-type',
})

_STYLE_VALUE_BANNED = ('expression', 'javascript:', 'url(', '@import', 'behavior')


def _safe_url(value):
    """Absolute urls on a known scheme, or root/relative paths. Anything with
    a scheme we do not recognize (javascript:, vbscript:, data:) is refused."""
    raw = (value or '').strip()
    # Control characters are how javascript&#58; style bypasses are smuggled in.
    cleaned = ''.join(ch for ch in raw if ch.isprintable() and ch not in '\t\r\n').strip()
    if not cleaned:
        return None
    lowered = cleaned.lower()
    if lowered.startswith(SAFE_SCHEMES):
        return cleaned
    # No scheme at all: a relative or root-relative path is fine.
    if ':' not in lowered.split('/')[0]:
        return cleaned
    return None


def _safe_style(value):
    """Filter a style attribute down to the allowlisted properties."""
    kept = []
    for declaration in (value or '').split(';'):
        if ':' not in declaration:
            continue
        prop, _, val = declaration.partition(':')
        prop = prop.strip().lower()
        val = val.strip()
        if prop not in ALLOWED_STYLE_PROPS or not val:
            continue
        lowered = val.lower()
        if any(bad in lowered for bad in _STYLE_VALUE_BANNED):
            continue
        kept.append(f"{prop}: {val}")
    return '; '.join(kept)


class _Sanitizer(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []
        self._drop_depth = 0        # inside a drop-with-content subtree
        self._open = []             # allowed tags awaiting their close

    # -- helpers

    def _attrs_html(self, tag, attrs):
        parts = []
        for name, value in attrs:
            name = (name or '').strip().lower()
            if name.startswith('on') or name not in ALLOWED_ATTRS:
                continue
            if value is None:
                continue
            if name in URL_ATTRS:
                value = _safe_url(value)
                if value is None:
                    continue
            elif name == 'style':
                value = _safe_style(value)
                if not value:
                    continue
            parts.append(f' {name}="{escape(str(value), quote=True)}"')
        # A link that leaves the email should not hand over the opener.
        if tag == 'a' and any(p.startswith(' target=') for p in parts):
            if not any(p.startswith(' rel=') for p in parts):
                parts.append(' rel="noopener noreferrer"')
        return ''.join(parts)

    # -- parser callbacks

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if self._drop_depth:
            if tag in DROP_WITH_CONTENT:
                self._drop_depth += 1
            return
        if tag in DROP_WITH_CONTENT:
            self._drop_depth = 1
            return
        if tag not in ALLOWED_TAGS:
            return          # unwrap: children still render
        self.out.append(f'<{tag}{self._attrs_html(tag, attrs)}>')
        if tag not in VOID_TAGS:
            self._open.append(tag)

    def handle_startendtag(self, tag, attrs):
        tag = tag.lower()
        if self._drop_depth or tag in DROP_WITH_CONTENT or tag not in ALLOWED_TAGS:
            return
        self.out.append(f'<{tag}{self._attrs_html(tag, attrs)}>')

    def handle_endtag(self, tag):
        tag = tag.lower()
        if self._drop_depth:
            if tag in DROP_WITH_CONTENT:
                self._drop_depth -= 1
            return
        if tag in VOID_TAGS or tag not in ALLOWED_TAGS:
            return
        if tag in self._open:
            # Close anything left open inside it, so unbalanced input cannot
            # leak an open tag into the rest of the email.
            while self._open:
                open_tag = self._open.pop()
                self.out.append(f'</{open_tag}>')
                if open_tag == tag:
                    break

    def handle_data(self, data):
        if self._drop_depth:
            return
        self.out.append(escape(data, quote=False))

    def handle_comment(self, data):
        return          # conditional comments are an email-client attack surface

    def handle_decl(self, decl):
        return

    def unknown_decl(self, data):
        return

    def handle_pi(self, data):
        return

    def result(self):
        while self._open:
            self.out.append(f'</{self._open.pop()}>')
        return ''.join(self.out)


def sanitize_html(html):
    """Allowlisted HTML, safe to drop into an email body."""
    if not html:
        return ''
    parser = _Sanitizer()
    try:
        parser.feed(str(html))
        parser.close()
    except Exception:
        # Never let malformed input take a send down; fall back to text.
        logger.warning("sanitizer failed; falling back to escaped text", exc_info=True)
        return escape(str(html), quote=False)
    return parser.result()
