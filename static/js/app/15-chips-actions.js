document.addEventListener('DOMContentLoaded', () => {
    const selector = document.getElementById('email_list_selector');
    const deleteBtn = document.getElementById('delete_list_btn');
    const saveContainer = document.getElementById('save_list_container');
    const newListNameInput = document.getElementById('new_list_name');
    const saveBtn = document.getElementById('save_list_btn');
    const cancelBtn = document.getElementById('cancel_save_btn');
    const bccChipsContainer = document.getElementById('bcc_chips');
    const emailInput = document.getElementById('email_chip_input');
    
    function collectEmailsFromChips() {
        return Array.from(document.querySelectorAll('#bcc_chips .nl-chip'))
            .map(ch => ch.dataset.email)
            .filter(Boolean);
    }
    
    function clearAllChips() {
        document.querySelectorAll('#bcc_chips .nl-chip').forEach(chip => chip.remove());
    }
    
    function addEmailChip(email) {
        if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return;
        const sel = `.nl-chip[data-email="${CSS.escape(email)}"]`;
        if (bccChipsContainer.querySelector(sel)) return;

        const label = window.getEmailDisplayLabel ? window.getEmailDisplayLabel(email) : email;
        const chip = document.createElement('span');
        chip.className = 'nl-chip';
        chip.dataset.email = email;
        chip.innerHTML = `
            <span>${escapeHtml(label)}</span>
            <button type="button" class="remove" aria-label="Remove ${escapeHtml(label)}">x</button>
        `;
        bccChipsContainer.appendChild(chip);
    }

    function sortEmails(emails) {
        return window.sortEmailsByLabel ? window.sortEmailsByLabel(emails) : emails;
    }
    
    function setReadOnlyMode(readOnly) {
        const chips = document.querySelectorAll('#bcc_chips .nl-chip .remove');
        chips.forEach(btn => {
            btn.style.display = readOnly ? 'none' : 'inline';
        });
        emailInput.disabled = readOnly;
        if (readOnly) {
            emailInput.placeholder = 'Read-only mode';
        } else {
            emailInput.placeholder = 'Add BCC emails';
        }
    }
    
    const importBtn = document.getElementById('import_list_btn');
    const exportBtn = document.getElementById('export_list_btn');
    const importContainer = document.getElementById('import_list_container');
    const importFile = document.getElementById('import_list_file');
    const importText = document.getElementById('import_list_text');
    const importNameRow = document.getElementById('import_list_name_row');
    const importName = document.getElementById('import_list_name');
    const doImportBtn = document.getElementById('do_import_btn');
    const cancelImportBtn = document.getElementById('cancel_import_btn');
    const importResult = document.getElementById('import_result');

    function selectedListId() {
        const value = selector.value;
        return (value && !isNaN(Number(value))) ? value : null;
    }

    function hideImportUI() {
        if (!importContainer) return;
        importContainer.classList.add('d-none');
        if (importResult) importResult.textContent = '';
        if (importText) importText.value = '';
        if (importFile) importFile.value = '';
    }

    // With a saved list selected the import appends to it; otherwise it names a
    // list to create, which is the only way to import your first one.
    function syncImportMode() {
        if (!importNameRow) return;
        importNameRow.classList.toggle('d-none', !!selectedListId());
    }

    selector.addEventListener('change', async () => {
        const selectedValue = selector.value;

        deleteBtn.classList.add('d-none');
        saveContainer.classList.add('d-none');
        if (exportBtn) exportBtn.classList.add('d-none');
        hideImportUI();
        syncImportMode();

        if (selectedValue === 'Custom') {
            setReadOnlyMode(false);
        } else if (selectedValue === 'ALL') {
            clearAllChips();
            sortEmails(allUserEmails).forEach(email => addEmailChip(email));
            setReadOnlyMode(true);
        } else if (selectedValue === '(Save new list)') {
            saveContainer.classList.remove('d-none');
            newListNameInput.focus();
            setReadOnlyMode(false);
        } else {
            const option = selector.querySelector(`option[value="${selectedValue}"]`);
            if (option) {
                const emails = option.dataset.emails;
                clearAllChips();
                sortEmails(emails.split(', ').map(e => e.trim())).forEach(email => addEmailChip(email));
                deleteBtn.classList.remove('d-none');
                if (exportBtn) {
                    exportBtn.classList.remove('d-none');
                    exportBtn.href = `/email_lists/${encodeURIComponent(selectedValue)}/export`;
                }
                setReadOnlyMode(false);
            }
        }
    });

    if (importBtn) {
        importBtn.addEventListener('click', () => {
            importContainer.classList.toggle('d-none');
            syncImportMode();
            if (!importContainer.classList.contains('d-none') && importText) importText.focus();
        });
    }
    if (cancelImportBtn) {
        cancelImportBtn.addEventListener('click', hideImportUI);
    }
    if (doImportBtn) {
        doImportBtn.addEventListener('click', async () => {
            const listId = selectedListId();
            const newName = importName ? importName.value.trim() : '';
            if (!listId && !newName) {
                alert('Enter a name for the new list');
                return;
            }
            const file = importFile && importFile.files && importFile.files[0];
            const pasted = importText ? importText.value.trim() : '';
            if (!file && !pasted) {
                alert('Choose a file or paste some addresses');
                return;
            }
            const url = listId ? `/email_lists/${listId}/import` : '/email_lists/import';

            doImportBtn.disabled = true;
            try {
                let response;
                if (file) {
                    const body = new FormData();
                    body.append('file', file);
                    if (!listId) body.append('name', newName);
                    response = await fetch(url, {
                        method: 'POST',
                        headers: { 'X-CSRF-Token': APP.csrfToken },
                        body: body,
                    });
                } else {
                    const payload = { text: pasted };
                    if (!listId) payload.name = newName;
                    response = await fetch(url, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRF-Token': APP.csrfToken,
                        },
                        body: JSON.stringify(payload),
                    });
                }
                const result = await response.json();
                if (result.status !== 'success') {
                    importResult.textContent = result.message || 'Import failed';
                    return;
                }
                // Every category is reported, so a partly rejected file is
                // visible rather than silently lossy.
                const parts = [`${result.added} added`];
                if (result.duplicate) parts.push(`${result.duplicate} already on the list`);
                if (result.suppressed) parts.push(`${result.suppressed} unsubscribed`);
                if (result.invalid_count) parts.push(`${result.invalid_count} unreadable`);
                if (result.linked) parts.push(`${result.linked} linked to Jellyfin users`);
                importResult.textContent = parts.join(', ') + '.';

                // A freshly created list is not in the dropdown yet, so add it
                // and select it: landing back on Custom would leave the list you
                // just built invisible.
                const targetId = listId || result.list_id;
                if (!listId && targetId) {
                    let option = selector.querySelector(`option[value="${targetId}"]`);
                    if (!option) {
                        option = document.createElement('option');
                        option.value = targetId;
                        option.textContent = result.list_name || newName;
                        selector.appendChild(option);
                    }
                    selector.value = String(targetId);
                    deleteBtn.classList.remove('d-none');
                    if (exportBtn) {
                        exportBtn.classList.remove('d-none');
                        exportBtn.href = `/email_lists/${targetId}/export`;
                    }
                    syncImportMode();
                }

                // Refresh the chips and the option's cached addresses so the
                // selector does not go stale against what was just imported.
                const contacts = await (await fetch(`/email_lists/${targetId}/contacts`)).json();
                if (contacts.status === 'success') {
                    const emails = contacts.contacts.map(c => c.email);
                    const option = selector.querySelector(`option[value="${targetId}"]`);
                    if (option) option.dataset.emails = emails.join(', ');
                    clearAllChips();
                    sortEmails(emails).forEach(email => addEmailChip(email));
                }
            } catch (e) {
                importResult.textContent = 'Import failed';
            } finally {
                doImportBtn.disabled = false;
            }
        });
    }
    
    saveBtn.addEventListener('click', async () => {
        const name = newListNameInput.value.trim();
        if (!name) {
            alert('Please enter a list name');
            return;
        }
        
        const emails = collectEmailsFromChips();
        if (emails.length === 0) {
            alert('Cannot save empty email list');
            return;
        }
        
        try {
            const response = await fetch('/email_lists', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRF-Token': APP.csrfToken,
                },
                body: JSON.stringify({
                    name: name,
                    emails: emails.join(', ')
                })
            });
            
            const result = await response.json();
            if (result.status === 'success') {
                const newOption = document.createElement('option');
                newOption.value = 'temp_' + Date.now();
                newOption.textContent = name;
                newOption.dataset.emails = emails.join(', ');
                selector.insertBefore(newOption, selector.querySelector('option[value="(Save new list)"]'));
                
                selector.value = newOption.value;
                saveContainer.classList.add('d-none');
                newListNameInput.value = '';
                deleteBtn.classList.remove('d-none');
                
                alert(result.message);
                
                setTimeout(() => window.location.reload(), 1000);
            } else {
                alert(result.message);
            }
        } catch (error) {
            alert('Error saving list: ' + error.message);
        }
    });
    
    cancelBtn.addEventListener('click', () => {
        saveContainer.classList.add('d-none');
        newListNameInput.value = '';
        selector.value = 'Custom';
    });
    
    deleteBtn.addEventListener('click', async () => {
        const selectedValue = selector.value;
        const option = selector.querySelector(`option[value="${selectedValue}"]`);
        
        if (!option || !confirm(`Delete list "${option.textContent}"?`)) return;
        
        try {
            const response = await fetch(`/email_lists/${selectedValue}`, {
                method: 'DELETE',
                headers: { 'X-CSRF-Token': APP.csrfToken }
            });
            
            const result = await response.json();
            if (result.status === 'success') {
                option.remove();
                selector.value = 'Custom';
                deleteBtn.classList.add('d-none');
                alert(result.message);
            } else {
                alert(result.message);
            }
        } catch (error) {
            alert('Error deleting list: ' + error.message);
        }
    });
    
    setReadOnlyMode(false);
});
