document.getElementById('pullRecsBtn').addEventListener('click', async () => {
    showSpinner('Pulling recommendations...');

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
            newAlertP.style.display = '';
            oldAlertP.replaceWith(newAlertP);

        }

        const oldErrorP = document.getElementById('error_p');
        const newErrorP = doc.getElementById('error_p');
        if (oldErrorP && newErrorP) {
            newErrorP.style.display = '';
            oldErrorP.replaceWith(newErrorP);
        }

        const oldData = document.getElementById('recommendations-json');
        const newData = doc.getElementById('recommendations-json');
        if (newData) {
            if (oldData) oldData.replaceWith(newData); else document.body.appendChild(newData);
            window.recommendationsData = JSON.parse(document.getElementById('recommendations-json').textContent);
        }

        buildRecsUserRows();
    } catch (err) {
        console.error("Error pulling recommendations:", err);
        const error_p= document.getElementById('error_p');
        error_p.textContent = err;
        alert("Something went wrong while pulling recommendations.");
    } finally {
        try { hideSpinner(); } catch(_) {}
    }
});
