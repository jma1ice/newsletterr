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
