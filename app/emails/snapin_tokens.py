# Snap-in tokens in custom HTML (NEWS-32).
#
# Grammar: {{snapin:NAME}} and {{snapin:NAME:ARG}} (recently_added takes an
# optional second ARG for the per-library count). Each supported name maps
# onto the assemble per-item dispatch; expansion synthesizes the equivalent
# selected_item and renders it through the exact same code path, so tokens
# are layout-aware and preview-mode aware for free. Graphs are excluded:
# their images are captured client-side per builder item and custom HTML has
# no items to carry them.
import re

import logging

logger = logging.getLogger(__name__)

TOKEN_RE = re.compile(r'\{\{\s*snapin:([A-Za-z_]+)((?::[^:{}]*)*)\s*\}\}')

# NAMEs that take no argument, mapped to their dispatch item type.
SIMPLE_TOKEN_TYPES = {
    'wrapped': 'yearly_wrapped',
    'coming_soon_tv': 'sonarr_coming_soon',
    'coming_soon_movies': 'radarr_coming_soon',
    'requests_ombi': 'ombi_requests',
    'requests_seerr': 'seerr_requests',
    'dn_server': 'droppedneedle_server_stats',
}

def synthesize_snapin_item(name, args, stats):
    """The selected_item dict equivalent to a token, or None when the name
    (or a required argument) does not resolve."""
    name = name.lower()

    if name == 'recently_added':
        item = {'id': 'token-recently-added', 'type': 'recently added'}
        if args and args[0]:
            item['raLibrary'] = args[0]
        if len(args) > 1 and args[1]:
            item['raCount'] = args[1]
        return item

    if name == 'most_watched':
        item = {'id': 'token-most-watched', 'type': 'most_watched'}
        if args and args[0]:
            item['mwLibrary'] = args[0]
        if len(args) > 1 and args[1]:
            item['mwCount'] = args[1]
        return item

    if name == 'random_pick':
        if not args or not args[0]:
            return None
        return {'id': 'token-random-pick', 'type': 'random_pick', 'library': args[0]}

    if name == 'stats':
        # The dispatch addresses stats by index ('stat-<n>'); the token names
        # them by title, so resolve against the cached stats list here.
        if not args or not args[0]:
            return None
        wanted = args[0].strip().lower()
        for index, stat in enumerate(stats or []):
            if (stat.get('stat_title') or '').strip().lower() == wanted:
                return {'id': f'stat-{index}', 'name': stat.get('stat_title'), 'type': 'stat'}
        return None

    if name in SIMPLE_TOKEN_TYPES:
        return {'id': f'token-{name}', 'type': SIMPLE_TOKEN_TYPES[name]}

    return None

def _unknown_token_comment(token_text):
    # visible in view-source so authors can spot typos without breaking the
    # email; '--' would terminate the comment early, so soften it
    safe = token_text.replace('--', '- -')
    return f'<!-- newsletterr: unknown snapin token {safe} -->'

def expand_snapin_tokens(html, render_item, stats=None):
    """Replace every {{snapin:...}} token in html with its rendered section.
    render_item is the assemble dispatch closure; the surrounding HTML is the
    author's and passes through untouched."""
    def _sub(match):
        name = match.group(1)
        raw_args = match.group(2) or ''
        args = [a.strip() for a in raw_args.split(':')[1:]] if raw_args else []
        item = synthesize_snapin_item(name, args, stats or [])
        if item is None:
            logger.debug(f"Unknown snapin token in custom HTML: {match.group(0)}")
            return _unknown_token_comment(match.group(0))
        return render_item(item)

    return TOKEN_RE.sub(_sub, html)
