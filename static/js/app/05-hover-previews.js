function showRAPreviewFor(libName) {
    const preview = document.getElementById('ra-preview');
    const ul = document.getElementById('ra-view');
    const list = items.filter(i => i.library === libName);
    ul.style.gridTemplateColumns = 'repeat(5, 1fr)';
    renderRAGrid(list, ul);
    preview.style.display = 'block';
}

function showRecsPreviewFor(userKey) {
    const preview = document.getElementById('recs-preview');
    if (!preview) return;
    const header = preview.querySelector('.card-header');
    if (header) header.textContent = `Recommendations - ${userDict[userKey] || userKey}`;
    const body = preview.querySelector('.card-body');
    body.innerHTML = '';
    body.appendChild(buildRecsBlockForUser(userKey, { headingTag: 'h4' }, { bgColorway: 'view' }));
    preview.style.display = 'block';
}

document.addEventListener('click', (e) => {
    if (e.target.classList.contains('view-stat-btn')) {
        const targetId = e.target.dataset.target;
        const previewDiv = document.getElementById('stat-preview');
        const allStats = document.querySelectorAll('.stat-table');
        
        allStats.forEach(el => el.classList.add('d-none'));
        
        document.getElementById(targetId).classList.remove('d-none');
        previewDiv.style.display = 'block';
    }
        
    if (e.target.classList.contains('view-graph-btn')) {
        const targetId = e.target.dataset.target;
        const previewDiv = document.getElementById('graph-preview');
        const allGraphs = document.querySelectorAll('.graph-table');
        
        allGraphs.forEach(el => el.classList.add('d-none'));
        
        const container = document.getElementById(targetId);
        container.classList.remove('d-none');
        previewDiv.style.display = 'block';
        
        if (!renderedCharts.has(targetId)) {
            const index = parseInt(targetId.split('-')[1]);
            const graphData = graphDataList[index];

            Highcharts.chart(targetId, {
                chart: { type: 'line' },
                title: { text: graphCommands[index].name },
                exporting: {
                    enabled: true
                },
                xAxis: { categories: graphData.categories },
                yAxis: { title: { text: hideGraphPlayCounts ? null : (statType === 'duration' ? 'Duration' : 'Plays') }, labels: { enabled: !hideGraphPlayCounts } },
                tooltip: hideGraphPlayCounts ? { enabled: false } : {},
                series: graphData.series
            });

            renderedCharts.add(targetId);
        }
        
        const nowDark = document.documentElement.classList.contains('dark');
        applyChartTheme(nowDark);
    }

    if (e.target.classList.contains('ra-view-btn')) {
        const viewBtn = e.target.closest('.ra-view-btn');
        if (viewBtn) {
            const lib = viewBtn.dataset.lib;
            showRAPreviewFor(lib);
            return;
        }
    }

    if (e.target.classList.contains('recs-view-btn')) {
        const viewBtn = e.target.closest('.recs-view-btn');
        if (viewBtn) {
            const userKey = viewBtn.dataset.userKey;
            if (userKey) showRecsPreviewFor(userKey);
            return;
        }
    }
});
