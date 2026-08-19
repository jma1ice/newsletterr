"""Guard: snap-in rows must not be permanently draggable."""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BUILDER_JS = REPO_ROOT / "static/js/app/07-email-builder.js"


def _source():
    return BUILDER_JS.read_text(encoding="utf-8")


def test_no_selected_item_row_renders_as_draggable():
    assert 'draggable="true"' not in _source()


def test_every_row_template_states_draggable_false():
    """Explicit over absent, so the intent survives the next edit."""
    source = _source()
    rows = re.findall(r'class="selected-item[^"]*"[^>]*?>', source, re.S)
    assert rows, "no selected-item row templates found"
    for row in rows:
        assert 'draggable="false"' in row, row


def test_drag_is_armed_on_mousedown_away_from_controls():
    source = _source()
    assert "DRAG_EXEMPT_SELECTOR" in source
    for control in ("input", "textarea", "select", "button", "contenteditable"):
        assert control in source.split("DRAG_EXEMPT_SELECTOR =")[1].split("\n")[0]
    assert re.search(
        r"addEventListener\('mousedown',.*?item\.draggable\s*=\s*!\(", source, re.S
    ), "rows are no longer armed on mousedown"


def test_drag_scroller_is_wired_through_the_whole_drag_lifecycle():
    source = _source()
    assert "dragScroller" in source, "autoscroll driver is gone"
    for hook, call in (
        ("dragstart", "dragScroller.start("),
        ("dragover", "dragScroller.update("),
        ("dragend", "dragScroller.stop()"),
    ):
        assert call in source, f"{hook} no longer drives the autoscroller"


def test_autoscroll_resolves_its_container_instead_of_hardcoding_one():
    """The scrollable ancestor differs by layout mode (pane at full width, the
    page at mid width and under snapins-static), so it must be resolved."""
    source = _source()
    assert "function scrollableAncestor(" in source
    start = source.index("function scrollableAncestor(")
    body = source[start:source.index("\n}", start)]
    assert "overflowY" in body and "scrollHeight" in body
    assert "selected-items-list" not in body, "container is hardcoded again"


def test_container_also_feeds_the_scroller():
    """Pointer over container padding fires no per-row dragover, which is
    exactly where it lands when reaching for the edge of the list."""
    source = _source()
    assert "dragScrollBound" in source, "container-level dragover binding is gone"


def test_every_row_offers_move_to_top_and_bottom():
    """Derived from the row-template count rather than a literal, so adding a
    new snap-in row type without move controls fails here."""
    source = _source()
    assert "function itemMoveControls(" in source
    row_templates = len(re.findall(r'class="selected-item[^"]*"[^>]*?>', source, re.S))
    assert row_templates, "no selected-item row templates found"
    assert source.count("itemMoveControls(index, selectedItems.length)") == row_templates
    for edge in ('data-edge="top"', 'data-edge="bottom"'):
        assert edge in source


def test_move_controls_are_disabled_at_the_ends():
    source = _source()
    start = source.index("function itemMoveControls(")
    body = source[start:source.index("\nfunction ", start + 1)]
    assert "index === 0 ? 'disabled' : ''" in body
    assert "index === total - 1 ? 'disabled' : ''" in body


def test_move_handler_reads_the_button_not_the_click_target():
    """The arrows are SVG-only, so e.target is the <svg> on a center click."""
    source = _source()
    start = source.index("if (btn.classList.contains('item-move-btn'))")
    body = source[start:start + 300]
    assert "btn.dataset.index" in body
    assert "btn.dataset.edge" in body
    assert "e.target.dataset" not in body


BUILDER_CSS = REPO_ROOT / "static/css/pages/builder.css"


def _css():
    return BUILDER_CSS.read_text(encoding="utf-8")


def test_dragging_style_outranks_the_hover_style():
    css = _css()
    hover = css.index(".selected-item:hover {")
    dragging = css.index(".selected-item.dragging")
    assert dragging > hover, ".dragging moved back above :hover"
    assert ".selected-item.dragging:hover" in css


def test_dragging_class_is_also_applied_from_the_drag_event():
    """Safari can hold the dragstart setTimeout until the drag session ends."""
    source = _source()
    assert "const markDragging" in source
    assert "addEventListener('drag', markDragging)" in source
    assert "setTimeout(markDragging, 0)" in source


def test_list_scroll_position_survives_a_rebuild():
    """A drop rebuilds the list from innerHTML; without this the user is
    thrown back to the first snap-in instead of where they dropped."""
    source = _source()
    start = source.index("function updateSelectedItemsDisplay()")
    body = source[start:source.index("\nfunction ", start + 1)]
    assert "prevScrollTop = container ? container.scrollTop : 0" in body
    assert "container.scrollTop = prevScrollTop" in body


def test_floating_pane_list_carries_its_own_height_cap():
    """WebKit does not reliably shrink the flex child when the only limit is
    the pane's max-height, which let the pane grow with every item added."""
    css = _css()
    start = css.index("#selected-items-pane > #selected-items-list {")
    body = css[start:css.index("}", start)]
    assert "max-height: calc(" in body, "cap is back to max-height: none"
    assert "overflow-y: auto" in body
