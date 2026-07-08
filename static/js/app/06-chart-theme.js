function themeVars(isDark) {
    return {
        text: isDark ? '#8acbd4' : '#333',
        grid: isDark ? '#e5e7eb' : '#374151',
        axis: isDark ? '#e5e7eb' : '#374151',
        bg: isDark ? '#333' : '#8acbd4',
    };
}

function applyChartTheme(isDark) {
    const t = themeVars(isDark);

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

const isDark = document.documentElement.classList.contains('dark');
applyChartTheme(isDark);

document.getElementById('theme-toggle')?.addEventListener('click', () => {
    const nowDark = document.documentElement.classList.contains('dark');
    applyChartTheme(!nowDark);
});
