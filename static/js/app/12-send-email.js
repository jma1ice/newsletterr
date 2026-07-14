function collectEmailsFromChips() {
    return Array.from(document.querySelectorAll('#bcc_chips .nl-chip'))
        .map(ch => ch.dataset.email)
        .filter(Boolean);
}

async function buildEmailPayload() {
    const subject = document.getElementById('subject').value;
    const emailHeaderTitle = document.getElementById('email_header_title').value;

    const previewFrame = document.getElementById('preview');
    const previewDoc = previewFrame.contentDocument || previewFrame.contentWindow.document;
    const emailHTML = previewDoc.documentElement.outerHTML;

    for (let item of selectedItems) {
        if (item.type === 'graph' && !item.chartImage) {
            const chartImage = await captureChartAsBase64(item.id);
            if (chartImage) {
                item.chartImage = chartImage;
            }
        }
    }

    selectedItems.forEach(item => {
        if (['textblock', 'titleblock', 'headerblock'].includes(item.type)) {
            item.content = getTextBlockContent(item.id);
        }
    });

    return {
        subject,
        email_header_title: emailHeaderTitle,
        email_html: emailHTML,
        selected_items: selectedItems,
        user_dict: userDict,
        expanded_collections: convertExpandedCollectionsForBackend(),
        custom_html: document.getElementById('custom-html-toggle')?.checked ? (document.getElementById('custom-html-editor')?.value || '') : ''
    };
}

function describeSendResult(data, fallbackCount) {
    if (Array.isArray(data.sent_groups)) {
        const n = data.sent_groups.length;
        return `Email sent to ${n} user group${n !== 1 ? 's' : ''}.`;
    }
    if (data.sent_to) {
        return `Email sent (${data.sent_to}).`;
    }
    return `Email sent to ${fallbackCount} recipient${fallbackCount !== 1 ? 's' : ''}.`;
}

document.getElementById('sendEmailBtn').addEventListener('click', async () => {
    const subject = document.getElementById('subject').value;

    const chipInput = document.getElementById('email_chip_input');
    if (chipInput && chipInput.value.trim()) {
        chipInput.dispatchEvent(new Event('blur'));
    }

    const toList = collectEmailsFromChips();
    if (!toList.length) {
        alert('Please add at least one recipient.');
        return;
    }

    const ok = window.confirm(
        `Send email?\n\nSubject: ${subject || '(no subject)'}\n\nRecipients (${toList.length}):\n${toList.join('\n')}`
    );
    if (!ok) return;

    showSpinner('Preparing email content...');

    try {
        const payload = await buildEmailPayload();
        payload.to_emails = toList.join(', ');

        // Large-email guard: measure the rendered preview HTML and confirm
        // before sending if it exceeds the configured threshold. The estimate
        // excludes server-side CID image attachment overhead.
        const warnMb = parseFloat(APP.settings?.email_size_warn_mb ?? 10);
        if (warnMb > 0 && payload.email_html) {
            const mb = new Blob([payload.email_html]).size / (1024 * 1024);
            if (mb > warnMb) {
                hideSpinner();
                const proceed = window.confirm(
                    `This email is roughly ${mb.toFixed(1)} MB (estimated; excludes server-side image attachments), ` +
                    `over your ${warnMb} MB warning threshold. Large emails may be clipped or rejected by some providers.\n\nSend anyway?`
                );
                if (!proceed) return;
            }
        }

        showSpinner('Sending email...');

        const resp = await fetch('/send_email', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRF-Token': APP.csrfToken,
            },
            body: JSON.stringify(payload)
        });

        const data = await resp.json();
        if (resp.ok) {
            window.clearDraft?.();
            alert(describeSendResult(data, toList.length));
        } else {
            alert("Error sending email: " + (data.error || resp.statusText));
        }
    } catch (err) {
        console.error("Error sending email:", err);
        alert("Something went wrong while sending the email.");
    }

    hideSpinner();
});

document.getElementById('sendTestBtn')?.addEventListener('click', async () => {
    const subject = document.getElementById('subject').value;
    const testAddr = APP.settings?.from_email || 'your From address';
    if (!window.confirm(`Send a test copy of this email to ${testAddr}?\n\nSubject: ${subject || '(no subject)'}`)) return;

    showSpinner('Sending test email...');
    try {
        const payload = await buildEmailPayload();

        const resp = await fetch('/send_test_email', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRF-Token': APP.csrfToken,
            },
            body: JSON.stringify(payload)
        });

        const data = await resp.json();
        if (resp.ok) {
            alert(data.message || 'Test email sent.');
        } else {
            alert("Error sending test: " + (data.error || resp.statusText));
        }
    } catch (err) {
        console.error("Error sending test email:", err);
        alert("Something went wrong while sending the test email.");
    }
    hideSpinner();
});
