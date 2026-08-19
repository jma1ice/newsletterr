"""Guards against graphs shipping a stale picture.

A graph section is not rendered from data at send time the way a stats table
is. It ships as a PNG captured from a live Highcharts instance and attached by
app/emails/blocks.py, so the only thing keeping a chart honest is capturing it
against current data. Two ways that used to go wrong:

* The capture was taken once when the graph was added and then written into
  the template row, so loading that template mailed a chart from whenever the
  graph was first added. It also survived a stats pull inside one session,
  because nothing invalidated it.
* A scheduled send overwrote the capture only when the headless render
  produced one. When that render failed (no playwright browsers, a timeout)
  the item kept the image saved in the template and the send went out looking
  successful.

The JS half runs the real functions out of static/js/app/ through node.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from app.emails.scheduled import apply_chart_captures
from tests.js_helpers import _extract_js_function

REPO_ROOT = Path(__file__).resolve().parent.parent

STALE = "data:image/png;base64,CAPTURED-LAST-MONTH"
FRESH = {"dataUrl": "data:image/png;base64,CAPTURED-THIS-RUN"}


def test_capture_replaces_the_image_saved_in_the_template():
    items = [{"type": "graph", "id": "graph-3", "chartImage": STALE}]

    assert apply_chart_captures(items, {"graph-3": FRESH}) == []
    assert items[0]["chartImage"] == FRESH["dataUrl"]


def test_failed_capture_clears_rather_than_keeping_the_stale_image():
    items = [{"type": "graph", "id": "graph-3", "chartImage": STALE}]

    # what an environment without playwright browsers hands back
    assert apply_chart_captures(items, {}) == ["graph-3"]
    assert items[0]["chartImage"] == ""


def test_partial_capture_reports_only_the_missing_graph():
    items = [
        {"type": "graph", "id": "graph-1", "chartImage": STALE},
        {"type": "graph", "id": "graph-2", "chartImage": STALE},
        {"type": "stat", "id": "stat-0"},
    ]

    assert apply_chart_captures(items, {"graph-1": FRESH}) == ["graph-2"]
    assert items[0]["chartImage"] == FRESH["dataUrl"]
    assert items[1]["chartImage"] == ""
    assert "chartImage" not in items[2]


def test_empty_data_url_counts_as_a_failed_capture():
    items = [{"type": "graph", "id": "graph-3", "chartImage": STALE}]

    assert apply_chart_captures(items, {"graph-3": {"dataUrl": ""}}) == ["graph-3"]
    assert items[0]["chartImage"] == ""


# The template row is where a capture used to get frozen. Both the save and
# the load drop it: the save so new templates never carry one, the load so
# rows written before this still heal.
@pytest.mark.parametrize("func_name", ["saveCurrentTemplate", "loadTemplate"])
def test_templates_js_never_carries_a_chart_image_across(func_name):
    source = (REPO_ROOT / "static/js/app/16-templates.js").read_text()
    func = _extract_js_function(source, func_name)

    assert "chartImage" in func, (
        f"{func_name} no longer mentions chartImage; if the capture is not "
        "stripped here it gets persisted into the template row"
    )


pytestmark_node = pytest.mark.skipif(
    shutil.which("node") is None, reason="node is required for the JS tests"
)

# ensureChartImage decides whether a capture is still good. Stubs stand in for
# Highcharts: renderGraphChart records which data generation it drew, and the
# capture returns that generation, so a stale capture is visible in the result
# rather than inferred.
HARNESS = """
const renderedCharts = new Set();
let chartDataGeneration = 0;
let onScreen = null;
const log = [];

function renderGraphChart(id) {
    renderedCharts.add(id);
    onScreen = chartDataGeneration;
    log.push('render:' + chartDataGeneration);
    return true;
}

async function captureChartAsBase64(id) {
    log.push('capture:' + onScreen);
    return 'GEN' + onScreen;
}

// what pullStats does after new data lands
function pullStats() {
    renderedCharts.clear();
    chartDataGeneration++;
}

%(ensure)s

(async () => {
    %(body)s
})();
"""


def _run_js(body):
    source = (REPO_ROOT / "static/js/app/07-email-builder.js").read_text()
    # the extractor anchors on "function <name>", so async is not in what it returns
    ensure = "async " + _extract_js_function(source, "ensureChartImage")

    out = subprocess.run(
        ["node", "-e", HARNESS % {"ensure": ensure, "body": body}],
        capture_output=True, text=True, check=True,
    )
    return json.loads(out.stdout)


@pytestmark_node
def test_capture_happens_once_while_the_data_is_unchanged():
    """A settled chart must not be re-captured on every keystroke; each
    preview calls ensureChartImage for every graph."""
    result = _run_js("""
        const item = { id: 'graph-3', type: 'graph' };
        await ensureChartImage(item);
        await ensureChartImage(item);
        await ensureChartImage(item);
        console.log(JSON.stringify({ image: item.chartImage, log: log }));
    """)

    assert result["image"] == "GEN0"
    assert result["log"].count("capture:0") == 1


@pytestmark_node
def test_a_stats_pull_forces_a_redraw_and_a_new_capture():
    """The container in #graph-N keeps whatever Highcharts drew into it, so a
    pull has to redraw before capturing or the new capture is of the old
    chart."""
    result = _run_js("""
        const item = { id: 'graph-3', type: 'graph' };
        await ensureChartImage(item);
        pullStats();
        await ensureChartImage(item);
        console.log(JSON.stringify({ image: item.chartImage, log: log }));
    """)

    assert result["image"] == "GEN1"
    assert result["log"] == ["render:0", "capture:0", "render:1", "capture:1"]


@pytestmark_node
def test_an_image_from_an_older_session_is_discarded():
    """Belt and braces for template rows written before the save started
    stripping the capture."""
    result = _run_js("""
        const item = { id: 'graph-3', type: 'graph', chartImage: 'ANCIENT', chartGen: 0 };
        pullStats();
        await ensureChartImage(item);
        console.log(JSON.stringify({ image: item.chartImage, log: log }));
    """)

    assert result["image"] == "GEN1"
