function themeVars() {
    // Read live design tokens so charts follow the theme without hard-coded hex.
    const cs = getComputedStyle(document.documentElement);
    const v = (name, fallback) => (cs.getPropertyValue(name).trim() || fallback);
    return {
        text: v('--text', '#142226'),
        grid: v('--border', '#d0dfe1'),
        axis: v('--text-faint', '#8aa0a3'),
        bg: v('--surface-1', '#ffffff'),
    };
}

function applyChartTheme() {
    const t = themeVars();

    Highcharts.setOptions({
        chart: { backgroundColor: t.bg, style: { fontFamily: 'IBM Plex Sans' } },
        title: { style: { color: t.text } },
        legend: { itemStyle: { color: t.text } },
        xAxis: { labels: { style: { color: t.text } }, gridLineColor: t.grid, lineColor: t.axis, tickColor: t.axis },
        yAxis: { labels: { style: { color: t.text } }, title: { style: { color: t.text } }, gridLineColor: t.grid, lineColor: t.axis, tickColor: t.axis }
    });

    Highcharts.charts.filter(Boolean).forEach(c => {
        c.update({
            chart: { backgroundColor: t.bg },
            title: { style: { color: t.text } },
            legend: { itemStyle: { color: t.text } }
        });

        c.xAxis.forEach(ax => ax.update({
            labels: { style: { color: t.text } },
            gridLineColor: t.grid,
            lineColor: t.axis,
            tickColor: t.axis
        }));

        c.yAxis.forEach(ax => ax.update({
            labels: { style: { color: t.text } },
            title: { style: { color: t.text } },
            gridLineColor: t.grid,
            lineColor: t.axis,
            tickColor: t.axis
        }));

        c.redraw();
    });
}

applyChartTheme();

// Defer past the toggle handler that flips the .dark class so tokens are current.
document.getElementById('theme-toggle')?.addEventListener('click', () => {
    requestAnimationFrame(applyChartTheme);
});
