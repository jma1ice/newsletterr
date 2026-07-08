function collectEmailsFromChips() {
    return Array.from(document.querySelectorAll('#bcc_chips .nl-chip'))
        .map(ch => ch.dataset.email)
        .filter(Boolean);
}

document.getElementById('sendEmailBtn').addEventListener('click', async () => {
    const subject = document.getElementById('subject').value;
    const emailHeaderTitle = document.getElementById('email_header_title').value;
    
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

    const ok = window.confirm(
        `Send email?\n\nSubject: ${subject || '(no subject)'}\n\nRecipients (${toList.length}):\n${toList.join('\n')}`
    );
    if (!ok) return;

    showSpinner('Preparing email content...');

    try {
        const previewFrame = document.getElementById('preview');
        const previewDoc = previewFrame.contentDocument || previewFrame.contentWindow.document;
        const emailHTML = previewDoc.documentElement.outerHTML;

        for (let item of selectedItems) {
            if (item.type === 'graph' && !item.chartImage) {
                console.log('Capturing missing chart for:', item.id);
                const chartImage = await captureChartAsBase64(item.id);
                if (chartImage) {
                    item.chartImage = chartImage;
                }
            }
        }

        selectedItems.forEach(item => {
            if (['textblock', 'titleblock', 'headerblock'].includes(item.type)) {
                const content = getTextBlockContent(item.id);
                item.content = content;
            }
        });

        const expandedCollections = window.expandedCollections || {};

        showSpinner('Sending email...');

        const resp = await fetch('/send_email', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRF-Token': APP.csrfToken,
            },
            body: JSON.stringify({
                to_emails,
                subject,
                email_header_title: emailHeaderTitle,
                email_html: emailHTML,
                selected_items: selectedItems,
                user_dict: userDict,
                expanded_collections: convertExpandedCollectionsForBackend(),
                custom_html: document.getElementById('custom-html-toggle')?.checked ? (document.getElementById('custom-html-editor')?.value || '') : ''
            })
        });
        
        if (resp.ok) {
            const data = await resp.json();
            alert(`Email sent successfully to ${toList.length} recipient${toList.length !== 1 ? 's' : ''}!`);
        } else {
            const data = await resp.json();
            alert("Error sending email: " + data.error);
        }
    } catch (err) {
        console.error("Error sending email:", err);
        alert("Something went wrong while sending the email.");
    }

    hideSpinner();
});
