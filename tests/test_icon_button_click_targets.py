"""a click on an icon-only button must carry the button's data."""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BUILDER_JS = REPO_ROOT / "static/js/app/07-email-builder.js"
COMPONENTS_CSS = REPO_ROOT / "static/css/ui/components.css"


def test_no_click_handler_reads_dataset_off_the_click_target():
    """`e.target.dataset` in a click handler is the bug's signature.

    Reading `e.target.value` stays fine: those are input/select handlers, and
    form controls have no child elements to intercept the event.
    """
    source = BUILDER_JS.read_text(encoding="utf-8")
    offenders = re.findall(r"e\.target\.dataset\.\w+", source)
    assert not offenders, (
        "read the button via e.currentTarget.dataset instead: " + ", ".join(sorted(set(offenders)))
    )


def test_icons_inside_buttons_are_click_through():
    css = COMPONENTS_CSS.read_text(encoding="utf-8")
    rule = re.search(
        r"\.nl-btn \.nl-icon,\s*\.btn \.nl-icon\s*\{[^}]*pointer-events:\s*none",
        css,
        re.S,
    )
    assert rule, "the pointer-events guard on button icons is gone"


def test_the_collection_buttons_that_regressed_are_svg_and_stay_covered():
    source = BUILDER_JS.read_text(encoding="utf-8")
    for cls in (
        "expand-collection-btn",
        "media-upload-btn",
        "media-gif-search-btn",
        "collapse-ui-collection-btn",
    ):
        assert cls in source, f"{cls} disappeared; update this guard"

    # The peek toggle is an SVG now, not the old emoji.
    assert "function collectionPeekIcon(" in source
    assert "\U0001f441" not in source, "emoji glyph is back on a button"
