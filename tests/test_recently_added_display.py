"""Per-snap-in recently-added display options: the digest column count, the
grid/list orientation override, and the spotlight hero pick."""
import re

import pytest

THEME = {
    'background': '#0f0f0f', 'card_bg': '#181818', 'border': '#2b2b2b',
    'muted_text': '#8e8e8e', 'text': '#c9c9c9', 'accent': '#62a1a4',
    'primary': '#8acbd4', 'secondary': '#222222',
}


def _items(count):
    return [{
        'title': f'Title {i}',
        'rating_key': str(100 + i),
        'year': 2000 + i,
        'library_name': 'Movies',
        'duration': 5400000,
        'summary': 'A summary.',
        'plex_url': f'http://plex/{i}',
        'thumb': '/thumb.jpg',
    } for i in range(count)]


def _recent(count):
    return [{'recently_added': _items(count)}]


def _grouped_recent():
    return [
        {'recently_added': [
            dict(_items(1)[0], title='Library A older', rating_key='201', guid='plex://movie/a',
                 library_name='Movies', added_at='100', rating='8.0'),
            dict(_items(1)[0], title='Shared title', rating_key='202', guid='plex://movie/shared',
                 library_name='Movies', added_at='200', rating='7.0'),
        ]},
        {'recently_added': [
            dict(_items(1)[0], title='Library B newest', rating_key='301', guid='plex://movie/b',
                 library_name='Requested Movies', added_at='400', rating='6.0'),
            dict(_items(1)[0], title='Shared title', rating_key='302', guid='plex://movie/shared',
                 library_name='Requested Movies', added_at='300', rating='9.0'),
        ]},
    ]


@pytest.fixture()
def render(monkeypatch):
    """render_recently_added with image attachment stubbed out."""
    from app.emails.builders import layouts

    monkeypatch.setattr(layouts, 'fetch_and_attach_image', lambda *a, **k: None)

    def _render(layout, count=9, **kwargs):
        return layouts.render_recently_added(layout, _recent(count), None, THEME, **kwargs)

    return _render


def _titles(html):
    return re.findall(r'Title \d+', html)


# --- digest column count

def test_digest_renders_every_item_not_just_the_first_six(render):
    """The strip used to hard-stop at six posters in one row."""
    assert len(_titles(render('digest', count=9))) == 9


@pytest.mark.parametrize("cols,expected_rows,expected_cols", [(3, 3, 3), (5, 2, 5), (9, 1, 9), (12, 1, 9)])
def test_digest_wraps_at_the_configured_column_count(render, cols, expected_rows, expected_cols):
    html = render('digest', count=9, ra_grid_columns=cols)
    assert html.count('<tr>') == expected_rows
    # short rows are padded so the fixed table keeps its columns aligned, but a
    # snap-in with fewer items than columns narrows to its own item count
    assert html.count('<td') == expected_rows * expected_cols


def test_digest_shrinks_posters_as_columns_grow(render):
    wide = render('digest', count=10, ra_grid_columns=2)
    narrow = render('digest', count=10, ra_grid_columns=10)
    assert 'max-width: 74px' in wide
    assert 'max-width: 64px' in narrow


@pytest.mark.parametrize("layout", ("classic", "editorial", "digest"))
def test_grid_sizes_to_its_own_item_count_not_the_column_setting(render, layout):
    """Two snap-ins under one column setting each fill their own row: a six
    item library must not inherit the cell width of a ten item one."""
    six = render(layout, count=6, ra_grid_columns=10, orientation='grid')
    ten = render(layout, count=10, ra_grid_columns=10, orientation='grid')
    assert 'width: 16.6667%' in six
    assert 'width: 10.0000%' in ten
    # no dead cells padding the six item row out to ten columns
    assert 'width: 10.0000%' not in six


# --- orientation override

@pytest.mark.parametrize("layout", ("classic", "editorial", "digest", "spotlight"))
def test_blank_orientation_keeps_the_layouts_own_treatment(render, layout):
    assert render(layout, count=4) == render(layout, count=4, orientation='')


@pytest.mark.parametrize("layout", ("classic", "editorial", "digest", "spotlight"))
def test_both_orientations_render_every_item(render, layout):
    for orientation in ('grid', 'list'):
        html = render(layout, count=6, orientation=orientation)
        assert len(set(_titles(html))) == 6, f"{layout}/{orientation}"


@pytest.mark.parametrize("layout", ("classic", "editorial", "digest"))
def test_list_orientation_puts_one_item_per_row(render, layout):
    html = render(layout, count=6, orientation='list')
    grid = render(layout, count=6, orientation='grid')
    # a grid packs several titles between row boundaries; a list never does
    assert max(len(_titles(chunk)) for chunk in html.split('<tr')) == 1
    assert max(len(_titles(chunk)) for chunk in grid.split('<tr')) > 1


def test_grid_orientation_honors_the_column_count_in_every_layout(render):
    for layout in ('classic', 'editorial', 'digest'):
        html = render(layout, count=9, orientation='grid', ra_grid_columns=3)
        rows = [chunk for chunk in html.split('<tr') if _titles(chunk)]
        assert len(rows) == 3, layout
        assert all(len(_titles(row)) == 3 for row in rows), layout


def test_legacy_builder_takes_the_same_orientation(monkeypatch):
    from app.emails.builders import recently_added as ra

    monkeypatch.setattr(ra, 'fetch_and_attach_image', lambda *a, **k: 'cid:poster')
    grid = ra.build_recently_added_html_with_cids(_recent(4), None, THEME, ra_grid_columns=2)
    listed = ra.build_recently_added_html_with_cids(_recent(4), None, THEME, ra_grid_columns=2, orientation='list')

    assert grid.count('<tr') == 2
    assert listed.count('<tr') == 4
    assert len(set(_titles(listed))) == 4
    # both keep the section heading and the item metadata
    assert '>Recently Added</h2>' in listed
    assert '1h 30m' in listed


# --- grouped libraries

def test_grouped_libraries_merge_dedupe_sort_then_cap():
    from app.emails.builders.recently_added import recently_added_items

    picked = recently_added_items(
        _grouped_recent(), ['Movies', 'Requested Movies'], 'date')[:2]

    assert [item['title'] for item in picked] == ['Library B newest', 'Shared title']
    assert picked[1]['library_name'] == 'Requested Movies'


def test_grouped_libraries_honor_rating_sort():
    from app.emails.builders.recently_added import recently_added_items

    picked = recently_added_items(
        _grouped_recent(), ['Movies', 'Requested Movies'], 'rating')

    assert [item['title'] for item in picked] == [
        'Shared title', 'Library A older', 'Library B newest']


def test_grouped_rating_sort_treats_unparseable_ratings_as_zero():
    from app.emails.builders.recently_added import recently_added_items

    data = _grouped_recent()
    data[0]['recently_added'][0]['rating'] = 'unrated'

    picked = recently_added_items(data, ['Movies', 'Requested Movies'], 'rating')

    assert picked[-1]['title'] == 'Library A older'


def test_single_library_keeps_legacy_source_order():
    from app.emails.builders.recently_added import recently_added_items

    picked = recently_added_items(_grouped_recent(), 'Movies', 'date')

    assert [item['title'] for item in picked] == ['Library A older', 'Shared title']


def test_grouped_heading_names_every_library(render):
    html = render(
        'classic',
        count=1,
        library_filter=['Movies', 'Requested Movies'],
    )

    assert 'Recently Added - Movies + Requested Movies' in html


# --- spotlight hero pick

def test_spotlight_leads_with_the_first_item_by_default(render):
    html = render('spotlight', count=5)
    assert _hero(html) == 'Title 0'


def test_spotlight_leads_with_the_chosen_rating_key(render):
    assert _hero(render('spotlight', count=5, hero_key='103')) == 'Title 3'


def test_spotlight_accepts_a_title_when_the_pull_has_no_rating_key(render):
    assert _hero(render('spotlight', count=5, hero_key='Title 2')) == 'Title 2'


def test_a_hero_that_left_the_pull_falls_back_to_the_first_item(render):
    assert _hero(render('spotlight', count=5, hero_key='999')) == 'Title 0'


def test_the_hero_is_not_repeated_in_the_list_below(render):
    html = render('spotlight', count=5, hero_key='103')
    assert _titles(html).count('Title 3') == 1
    assert len(set(_titles(html))) == 5


def _hero(html):
    match = re.search(r'font-size: 21px.*?>(?:<a[^>]*>)?(Title \d+)', html, re.S)
    return match.group(1) if match else None


# --- token grammar

def test_recently_added_token_takes_a_count_and_an_orientation():
    from app.emails.snapin_tokens import synthesize_snapin_item

    assert synthesize_snapin_item('recently_added', ['Movies', '4', 'list'], []) == {
        'id': 'token-recently-added', 'type': 'recently added',
        'raLibrary': 'Movies', 'raCount': '4', 'raOrientation': 'list'}
    # either trailing position, so the count stays optional
    assert synthesize_snapin_item('recently_added', ['Movies', 'grid'], [])['raOrientation'] == 'grid'
    assert 'raOrientation' not in synthesize_snapin_item('recently_added', ['Movies', '4'], [])
