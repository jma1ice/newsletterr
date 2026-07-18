function showRecsCancelButton() {
    const spinner = document.getElementById('spinner');
    if (!spinner) return null;
    // Append inside the spinner card so the bordered box wraps the cancel button
    // along with the mascot and text; fall back to the overlay if absent.
    const host = spinner.querySelector('.spinner-card') || spinner;
    let btn = document.getElementById('recs-cancel-btn');
    if (!btn) {
        btn = document.createElement('button');
        btn.id = 'recs-cancel-btn';
        btn.type = 'button';
        btn.className = 'nl-btn nl-btn--danger nl-btn--sm mt-2';
        host.appendChild(btn);
    }
    btn.disabled = false;
    btn.textContent = 'Cancel';
    btn.onclick = async () => {
        btn.disabled = true;
        btn.textContent = 'Canceling...';
        const textEl = document.getElementById('loading-text');
        if (textEl) textEl.textContent = 'Canceling after the current user...';
        try {
            await fetch('/pull_recommendations/cancel', {
                method: 'POST',
                headers: { 'X-CSRF-Token': APP.csrfToken },
                credentials: 'same-origin'
            });
        } catch (_) { /* the pull will still finish and report status */ }
    };
    return btn;
}

function removeRecsCancelButton() {
    const btn = document.getElementById('recs-cancel-btn');
    if (btn) btn.remove();
}

document.getElementById('pullRecsBtn').addEventListener('click', async (e) => {
    if (!confirmFreshRepull(e.currentTarget, 'recommendations')) return;
    showSpinner('Pulling recommendations...');
    showRecsCancelButton();

    function collectEmailsFromChips() {
        return Array.from(document.querySelectorAll('#bcc_chips .nl-chip'))
            .map(ch => ch.dataset.email)
            .filter(Boolean);
    }

    const chipInput = document.getElementById('email_chip_input');
        if (chipInput && chipInput.value.trim()) {
            chipInput.dispatchEvent(new Event('blur'));
    }

    const toList = collectEmailsFromChips();
        if (!toList.length) {
            removeRecsCancelButton();
            try { hideSpinner(); } catch(_) {}
            alert('Please add at least one recipient.');
            return;
    }

    const to_emails = toList.join(', ');

    const payload = {
        stats: statsList,
        user_dict: userDict,
        graph_data: graphDataList,
        graph_commands: graphCommands,
        recent_data: recentPayload,
        libs: APP.libs,
        settings: APP.settings,
        to_emails
    };

    try {
        const resp = await fetch('/pull_recommendations', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'text/html',
                'X-CSRF-Token': APP.csrfToken,
            },
            body: JSON.stringify(payload),
            credentials: 'same-origin'
        });
        
        if (!resp.ok) throw new Error('Error pulling recommendations.');

        const html = await resp.text();
        const doc = new DOMParser().parseFromString(html, 'text/html');

        const oldCacheCard = document.getElementById('cache-card');
        const newCacheCard = doc.getElementById('cache-card');
        oldCacheCard.replaceWith(newCacheCard);

        const oldRecsRow = document.getElementById('recs-col');
        const newRecsRow = doc.getElementById('recs-col');
        oldRecsRow.replaceWith(newRecsRow);

        const oldRecsPreview = document.getElementById('recs-preview');
        const newRecsPreview = doc.getElementById('recs-preview');
        oldRecsPreview.replaceWith(newRecsPreview);

        const oldAlertP = document.getElementById('alert_p');
        const newAlertP = doc.getElementById('alert_p');
        if (oldAlertP && newAlertP) {
            newAlertP.style.display = newAlertP.textContent.trim() ? '' : 'none';
            oldAlertP.replaceWith(newAlertP);
        }

        const oldErrorP = document.getElementById('error_p');
        const newErrorP = doc.getElementById('error_p');
        if (oldErrorP && newErrorP) {
            newErrorP.style.display = newErrorP.textContent.trim() ? '' : 'none';
            oldErrorP.replaceWith(newErrorP);
        }

        const oldData = document.getElementById('recommendations-json');
        const newData = doc.getElementById('recommendations-json');
        if (newData) {
            if (oldData) oldData.replaceWith(newData); else document.body.appendChild(newData);
            window.recommendationsData = JSON.parse(document.getElementById('recommendations-json').textContent);
        }

        buildRecsUserRows();
        markPullCacheFresh('recommendations', true);
    } catch (err) {
        console.error("Error pulling recommendations:", err);
        const error_p= document.getElementById('error_p');
        error_p.textContent = err;
        alert("Something went wrong while pulling recommendations.");
    } finally {
        removeRecsCancelButton();
        try { hideSpinner(); } catch(_) {}
    }
});
