# Snap-in tokens in custom HTML (NEWS-32).
#
# Grammar: {{snapin:NAME}} and {{snapin:NAME:ARG}} (recently_added takes
# optional trailing ARGs for the per-library count and the grid/list
# orientation; the coming_soon names take an optional view word).
# Each supported name maps
# onto the assemble per-item dispatch; expansion synthesizes the equivalent
# selected_item and renders it through the exact same code path, so tokens
# are layout-aware and preview-mode aware for free. Graphs are excluded:
# their images are captured client-side per builder item and custom HTML has
# no items to carry them.
import re

from app.emails.builders.calendar_view import VIEWS as COMING_SOON_VIEWS

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
        # recently_added:<Library>[:count][:grid|list] - the orientation word
        # is accepted in either trailing position so a count stays optional.
        item = {'id': 'token-recently-added', 'type': 'recently added'}
        if args and args[0]:
            item['raLibrary'] = args[0]
        for arg in args[1:]:
            if not arg:
                continue
            if arg.lower() in ('grid', 'list'):
                item['raOrientation'] = arg.lower()
            else:
                item['raCount'] = arg
        return item

    if name == 'recently_released':
        # recently_released:<Library>[:count][:grid|list] - same grammar as
        # recently_added, since it renders through the same builders.
        item = {'id': 'token-recently-released', 'type': 'recently_released'}
        if args and args[0]:
            item['rrLibrary'] = args[0]
        for arg in args[1:]:
            if not arg:
                continue
            if arg.lower() in ('grid', 'list'):
                item['rrOrientation'] = arg.lower()
            else:
                item['rrCount'] = arg
        return item

    if name == 'most_watched':
        # most_watched:<Library>[:count][:recent] - 'recent' scopes plays to
        # the pull's time range instead of all-time counts. The scope word is
        # accepted in either trailing position so a count is optional.
        item = {'id': 'token-most-watched', 'type': 'most_watched'}
        if args and args[0]:
            item['mwLibrary'] = args[0]
        for arg in args[1:]:
            if not arg:
                continue
            if arg.lower() in ('recent', 'range', 'window'):
                item['mwScope'] = 'recent'
            else:
                item['mwCount'] = arg
        return item

    if name == 'featured_pick':
        if not args or not args[0]:
            return None
        return {'id': f'featured-pick-{args[0]}', 'type': 'featured_pick', 'title': args[0]}

    if name == 'top_viewer':
        return {'id': 'top-viewer', 'type': 'top_viewer'}

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
        item = {'id': f'token-{name}', 'type': SIMPLE_TOKEN_TYPES[name]}
        # coming_soon_tv|coming_soon_movies:<grid|calendar|agenda> - the view
        # word is the only argument these take; anything else is ignored so a
        # typo falls back to the layout default rather than dropping the item.
        if name.startswith('coming_soon') and args and args[0].lower() in COMING_SOON_VIEWS:
            item['csView'] = args[0].lower()
        return item

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
