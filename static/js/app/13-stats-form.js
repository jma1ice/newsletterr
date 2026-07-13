let allUserEmails = APP.allUserEmails;

function updateCacheBadge(cacheInfo, timeRange) {
    const badge = document.getElementById('cache-status-badge');
    if (!badge) return;

    const keys = ['stats', 'users', 'graph_data', 'recent_data', 'recommendations_json', 'filtered_users'];
    badge.innerHTML = keys.map(key => {
        const info = cacheInfo[key] || {};
        let statusHtml;
        if (info.exists) {
            if (info.is_fresh) {
                statusHtml = `<span class="text-success">✓ Fresh (${info.age_hours.toFixed(1)}h)</span>`;
            } else if (info.is_usable) {
                statusHtml = `<span class="text-warning">⚠ Old (${info.age_hours.toFixed(1)}h)</span>`;
            } else {
                statusHtml = `<span class="text-danger">✗ Expired</span>`;
            }
        } else {
            statusHtml = `<span class="text-muted">○ None</span>`;
        }
        const label = key.replace(/_/g, ' ');
        return `<div class="d-flex justify-content-between align-items-center mb-1">
            <span class="text-muted" style="text-transform: capitalize;">${label}:</span>
            ${statusHtml}
        </div>`;
    }).join('') + `<small class="text-muted d-block mt-2">Cache refreshes daily automatically. Use "Get Stats\\Users" to refresh manually.</small>`;
}

document.getElementById('stats_form').addEventListener('submit', async (e) => {
    e.preventDefault();
    showSpinner('Getting stats and users...');

    const time_range = document.getElementById('days_to_pull').value;
    const count = document.getElementById('items_to_pull').value;

    try {
        const resp = await fetch('/pull_stats', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRF-Token': APP.csrfToken,
            },
            body: JSON.stringify({ time_range, count }),
            credentials: 'same-origin'
        });

        if (!resp.ok) throw new Error('Failed to pull stats');
        const data = await resp.json();

        if (data.recent_data) {
            recentPayload.length = 0;
            data.recent_data.forEach(s => recentPayload.push(s));
            const host = document.getElementById('ra-lib-list');
            if (host) {
                host.innerHTML = '';
                buildRALibraryRows();
            }
            const raCard = document.getElementById('ra-card');
            if (raCard) raCard.style.display = '';
            const raHeader = document.getElementById('ra-header');
            if (raHeader) raHeader.style.display = '';
            if (host) host.style.display = '';
        }

        if (data.stats) {
            statsList = data.stats;
            buildStatsRows();
        }
        if (data.yearly_wrapped_json) {
            const yearlyWrappedScript = document.getElementById('yearly-wrapped-json');
            if (yearlyWrappedScript) yearlyWrappedScript.textContent = JSON.stringify(data.yearly_wrapped_json);
            buildYearlyWrappedRow();
        }
        if (data.graph_data) {
            graphDataList = data.graph_data;
            buildGraphsRows();
        }

        if (data.graph_commands) {
            graphCommands = data.graph_commands;
        }

        if (data.users_full_data) {
            usersFullData.length = 0;
            data.users_full_data.forEach(u => usersFullData.push(u));
        }

        if (data.cache_info) {
            updateCacheBadge(data.cache_info, data.time_range);
        }

        const alertEl = document.getElementById('alert_p');
        if (alertEl) {
            alertEl.textContent = data.alert || '';
            alertEl.style.display = data.alert ? '' : 'none';
        }

        const errorEl = document.getElementById('error_p');
        if (errorEl) {
            errorEl.textContent = data.error || '';
            errorEl.style.display = data.error ? '' : 'none';
        }

        if (data.user_dict && Object.keys(data.user_dict).length > 0) {
            const recsBtn = document.getElementById('pullRecsBtn');
            // Only re-enable if Conjurr is actually configured; otherwise the
            // button stays greyed with its explanatory tooltip.
            if (recsBtn && window.APP?.serviceFlags?.conjurr) {
                recsBtn.disabled = false;
                recsBtn.classList.remove('opacity-50', 'cursor-not-allowed');
            }
        }

        if (data.time_range) currentTimeRange = parseInt(data.time_range);

        renderedCharts.clear();
        updatePreview();

        if (data.user_dict) {
            Object.keys(userDict).forEach(k => delete userDict[k]);
            Object.assign(userDict, data.user_dict);

            allUserEmails.length = 0;
            Object.values(data.user_dict).filter(Boolean).forEach(e => allUserEmails.push(e));

            if (window.chipsClear && window.chipsAddTokens) {
                window.chipsClear();
                window.chipsAddTokens(Object.values(data.user_dict).join(', '));
            }

            const selector = document.getElementById('email_list_selector');
            if (selector) {
                const allOption = Array.from(selector.options).find(o => o.value === 'ALL');
                if (allOption) {
                    allOption.dataset.emails = Object.values(data.user_dict).join(', ');
                }
            }
        }
    } catch (err) {
        console.error('Error pulling stats:', err);
        const errorEl = document.getElementById('error_p');
        if (errorEl) errorEl.textContent = 'Something went wrong pulling stats.';
    } finally {
        hideSpinner();
    }
});
