document.addEventListener('DOMContentLoaded', () => {
    const clearCacheBtn = document.getElementById('clear_cache_btn');
    if (clearCacheBtn) {
        clearCacheBtn.addEventListener('click', async () => {
            try {
                clearCacheBtn.textContent = 'Clearing...';
                clearCacheBtn.disabled = true;
                
                const response = await fetch('/clear_cache', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRF-Token': APP.csrfToken,
                    }
                });
                
                if (response.ok) {
                    const result = await response.json();
                    const freshFlags = window.APP?.pullCacheFresh || {};
                    Object.keys(freshFlags).forEach(k => { freshFlags[k] = false; });
                    window.refreshCacheBadge?.();
                    clearCacheBtn.textContent = 'Cleared!';
                    clearCacheBtn.style.backgroundColor = '#28a745';
                    setTimeout(() => {
                        clearCacheBtn.textContent = 'Clear Cache';
                        clearCacheBtn.style.backgroundColor = '#dc3545';
                        clearCacheBtn.disabled = false;
                    }, 2000);
                } else {
                    throw new Error('Failed to clear cache');
                }
            } catch (error) {
                console.error('Error clearing cache:', error);
                clearCacheBtn.textContent = 'Error';
                clearCacheBtn.style.backgroundColor = '#dc3545';
                setTimeout(() => {
                    clearCacheBtn.textContent = 'Clear Cache';
                    clearCacheBtn.disabled = false;
                }, 2000);
            }
        });
    }
});

let emailTemplates = [];

async function loadEmailTemplates() {
    try {
        const response = await fetch('/email_templates');
        emailTemplates = await response.json();
        updateTemplateDropdown();
    } catch (error) {
        console.error('Error loading templates:', error);
    }
}

function updateTemplateDropdown() {
    const selector = document.getElementById('template-selector');
    
    while (selector.children.length > 2) {
        selector.removeChild(selector.lastChild);
    }
    
    emailTemplates.forEach(template => {
        const option = document.createElement('option');
        option.value = template.id;
        option.textContent = template.name;
        selector.appendChild(option);
    });
}

function openSaveTemplateDialog({ suggestedName = '', preselectId = null } = {}) {
    return new Promise((resolve) => {
        const modal = document.getElementById('saveTemplateModal');
        if (!modal) {   // dialog not on this page: fall back to the old flow
            const typed = prompt('Enter template name:');
            resolve(typed && typed.trim() ? typed.trim() : null);
            return;
        }

        const modeNew = document.getElementById('save_template_mode_new');
        const modeOverwrite = document.getElementById('save_template_mode_overwrite');
        const newPane = document.getElementById('save_template_new_pane');
        const overwritePane = document.getElementById('save_template_overwrite_pane');
        const nameInput = document.getElementById('save_template_name');
        const warning = document.getElementById('save_template_name_warning');
        const targetSelect = document.getElementById('save_template_target');
        const confirmBtn = document.getElementById('save_template_confirm_btn');

        targetSelect.innerHTML = '';
        emailTemplates.forEach(t => {
            const opt = document.createElement('option');
            opt.value = String(t.id);
            opt.textContent = t.name;
            targetSelect.appendChild(opt);
        });

        // Default to overwriting whatever is currently loaded, since that is
        // what someone editing a saved template almost always means.
        const hasTemplates = emailTemplates.length > 0;
        const preselect = preselectId != null && emailTemplates.some(t => String(t.id) === String(preselectId));
        modeOverwrite.disabled = !hasTemplates;
        modeOverwrite.checked = hasTemplates && preselect;
        modeNew.checked = !modeOverwrite.checked;
        if (preselect) targetSelect.value = String(preselectId);
        nameInput.value = suggestedName;

        function syncPanes() {
            const overwriting = modeOverwrite.checked;
            newPane.classList.toggle('d-none', overwriting);
            overwritePane.classList.toggle('d-none', !overwriting);
            confirmBtn.textContent = overwriting ? 'Overwrite' : 'Save';
            syncNameWarning();
        }

        // A new-template name that collides still overwrites, because the POST
        // upserts by name. Say so rather than letting it happen silently.
        function syncNameWarning() {
            if (modeOverwrite.checked) {
                warning.classList.add('d-none');
                return;
            }
            const typed = nameInput.value.trim().toLowerCase();
            const clash = typed && emailTemplates.some(t => t.name.trim().toLowerCase() === typed);
            warning.textContent = clash
                ? 'A template with this name already exists and will be replaced.'
                : '';
            warning.classList.toggle('d-none', !clash);
        }

        function cleanup() {
            modeNew.removeEventListener('change', syncPanes);
            modeOverwrite.removeEventListener('change', syncPanes);
            nameInput.removeEventListener('input', syncNameWarning);
            nameInput.removeEventListener('keydown', onKeydown);
            confirmBtn.removeEventListener('click', onConfirm);
            modal.removeEventListener('nl-modal-cancel', onCancel);
            document.removeEventListener('click', onDismiss, true);
            document.removeEventListener('keydown', onEscape, true);
        }

        function finish(value) {
            cleanup();
            window.NLModal.hide('saveTemplateModal');
            resolve(value);
        }

        function onConfirm() {
            if (modeOverwrite.checked) {
                const chosen = emailTemplates.find(t => String(t.id) === targetSelect.value);
                if (!chosen) return;
                finish(chosen.name);
            } else {
                const typed = nameInput.value.trim();
                if (!typed) { nameInput.focus(); return; }
                finish(typed);
            }
        }

        function onCancel() { finish(null); }
        function onKeydown(e) { if (e.key === 'Enter') { e.preventDefault(); onConfirm(); } }
        function onEscape(e) { if (e.key === 'Escape' && modal.classList.contains('show')) finish(null); }
        function onDismiss(e) {
            const el = e.target.closest && e.target.closest('[data-bs-dismiss="modal"]');
            if (el && modal.contains(el)) finish(null);
            else if (e.target.classList && e.target.classList.contains('nl-modal-backdrop-el')) finish(null);
        }

        modeNew.addEventListener('change', syncPanes);
        modeOverwrite.addEventListener('change', syncPanes);
        nameInput.addEventListener('input', syncNameWarning);
        nameInput.addEventListener('keydown', onKeydown);
        confirmBtn.addEventListener('click', onConfirm);
        document.addEventListener('click', onDismiss, true);
        document.addEventListener('keydown', onEscape, true);

        syncPanes();
        window.NLModal.show('saveTemplateModal');
    });
}

document.getElementById('template-selector').addEventListener('change', async function() {
    const value = this.value;
    const deleteBtn = document.getElementById('delete-template-btn');

    if (value === 'save-template') {
        const loadedId = document.getElementById('delete-template-btn')?.dataset.templateId || null;
        const templateName = await openSaveTemplateDialog({ preselectId: loadedId });
        if (templateName) {
            await saveCurrentTemplate(templateName);
        }
        this.value = '';
        deleteBtn.style.display = 'none';
    } else if (value === '') {
        deleteBtn.style.display = 'none';
    } else {
        const templateId = parseInt(value);
        const template = emailTemplates.find(t => t.id === templateId);
        if (template) {
            loadTemplate(template);
            deleteBtn.style.display = 'inline-block';
            deleteBtn.dataset.templateId = templateId;
        }
    }
});

document.getElementById('reset-template-btn').addEventListener('click', function() {
    if (confirm('Are you sure you want to reset? This will clear all selected items and reset to Custom template.')) {
        selectedItems.length = 0;
        
        document.getElementById('template-selector').value = '';
        
        document.getElementById('delete-template-btn').style.display = 'none';
        
        document.querySelectorAll('.add-stat-btn, .add-graph-btn, .ra-add-btn, .rr-add-btn, .mw-add-btn, .recs-add-btn, .droppedneedle-add-btn, .droppedneedle-server-add-btn, .yearly-wrapped-add-btn, .sonarr-coming-soon-add-btn, .radarr-coming-soon-add-btn, .ombi-requests-add-btn, .seerr-requests-add-btn, .top-viewer-add-btn').forEach(btn => {
            btn.textContent = 'Add';
            btn.classList.remove('nl-btn--success');
            btn.classList.add('nl-btn--primary');
            btn.disabled = false;
        });
        const editor = document.getElementById('custom-html-editor');
        if (editor) {
            editor.value = '';
            editor.dispatchEvent(new Event('input'));
        }
        
        updateSelectedItemsDisplay();

        textBlockCounter = 0;
        titleBlockCounter = 0;
        headerBlockCounter = 0;

        if (typeof window.clearDraft === 'function') window.clearDraft();
    }
});

async function saveCurrentTemplate(name) {
    try {
        const _isDefault = (raw, resolvedDefault) => {
            if (raw === resolvedDefault) return true;
            if (!resolvedDefault) return false;
            const norm = (s) => textBlockPlainText(s).replace(/\s+/g, ' ').trim();
            return norm(raw) === norm(resolvedDefault);
        };

        const _sentinelContent = (item) => {
            const raw = getTextBlockContent(item.id) || '';
            if (item.id.startsWith('intro-block-') && _isDefault(raw, _resolvedIntroDefault)) return '__DEFAULT_INTRO__';
            if (item.id.startsWith('outro-block-') && _isDefault(raw, _resolvedOutroDefault)) return '__DEFAULT_OUTRO__';
            return raw;
        };

        const textBlocks = selectedItems
            .filter(item => item.type === 'textblock' || item.type === 'titleblock' || item.type === 'headerblock')
            .map(item => _sentinelContent(item))
            .filter(content => content.trim().length > 0);

        const itemsWithContent = selectedItems.map(({ chartImage, chartGen, ...item }) => {
            if (item.type === 'textblock' || item.type === 'titleblock' || item.type === 'headerblock') {
                return { ...item, content: _sentinelContent(item) };
            }
            return item;
        });

        const isCustomHtml = document.getElementById('custom-html-toggle')?.checked || false;
        const customHtml = isCustomHtml ? (document.getElementById('custom-html-editor')?.value || '') : '';

        const templateData = {
            name: name,
            selected_items: JSON.stringify(itemsWithContent),
            email_text: textBlocks.join('\n\n'),
            subject: document.getElementById('subject').value,
            email_header_title: document.getElementById('email_header_title')?.value || '',
            expanded_collections: JSON.stringify(convertExpandedCollectionsForBackend()),
            custom_html: customHtml
        };

        const response = await fetch('/email_templates', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRF-Token': APP.csrfToken,
            },
            body: JSON.stringify(templateData)
        });

        const result = await response.json();
        if (result.status === 'success') {
            console.log('Template saved successfully');
            await loadEmailTemplates();
            if (typeof window.clearDraft === 'function') window.clearDraft();
        } else {
            alert('Error saving template: ' + result.message);
        }
    } catch (error) {
        console.error('Error saving template:', error);
        alert('Error saving template');
    }
}

function loadTemplate(template) {
    try {
        const items = JSON.parse(template.selected_items);
        const customHtml = template.custom_html || '';
        const toggle = document.getElementById('custom-html-toggle');
        const editor = document.getElementById('custom-html-editor');

        if (customHtml && toggle && editor) {
            toggle.checked = true;
            editor.value = customHtml;
            toggle.dispatchEvent(new Event('change'));
        } else if (toggle) {
            toggle.checked = false;
            toggle.dispatchEvent(new Event('change'));
        }

        selectedItems = [];
        
        document.querySelectorAll('.add-stat-btn, .add-graph-btn, .ra-add-btn, .rr-add-btn, .mw-add-btn, .recs-add-btn, .droppedneedle-add-btn, .droppedneedle-server-add-btn, .yearly-wrapped-add-btn, .sonarr-coming-soon-add-btn, .radarr-coming-soon-add-btn, .ombi-requests-add-btn, .seerr-requests-add-btn, .top-viewer-add-btn').forEach(btn => {
            btn.textContent = 'Add';
            btn.classList.remove('nl-btn--success');
            btn.classList.add('nl-btn--primary');
            btn.disabled = false;
        });
        
        selectedItems = items.map(({ chartImage, chartGen, ...item }) => {
            // chartImage is dropped on save now, but templates saved before
            // that carry one; discarding it here heals those rows instead of
            // mailing a chart captured months ago.
            const restored = { ...item };
            if (restored.type === 'textblock' || restored.type === 'titleblock' || restored.type === 'headerblock') {
                const counter = parseInt(restored.id.split('-')[2]);
                if (!Number.isNaN(counter)) {
                    if (restored.type === 'titleblock' && restored.id.startsWith('title-block-')) {
                        if (counter >= titleBlockCounter) titleBlockCounter = counter;
                    } else if (restored.type === 'headerblock' && restored.id.startsWith('header-block-')) {
                        if (counter >= headerBlockCounter) headerBlockCounter = counter;
                    } else if (counter >= textBlockCounter) {
                        textBlockCounter = counter;
                    }
                }
                if (restored.content === '__DEFAULT_INTRO__') restored.content = _resolvedIntroDefault;
                else if (restored.content === '__DEFAULT_OUTRO__') restored.content = _resolvedOutroDefault;
            }
            return restored;
        });

        window.collapsedCollectionsUI = {};
        if (template.expanded_collections) {
            try {
                window.expandedCollections = convertExpandedCollectionsFromBackend(
                    JSON.parse(template.expanded_collections)
                );
            } catch (e) {
                console.warn('Failed to parse expanded collections from template:', e);
                window.expandedCollections = {};
            }
        } else {
            window.expandedCollections = {};
        }
        
        selectedItems.forEach(item => {
            if (item.type === 'graph' && !renderedCharts.has(item.id)) {
                renderGraphChart(item.id);
            }
        });
        
        selectedItems.forEach(item => {
            const button = document.querySelector(`[data-id="${item.id}"]`);
            if (button) {
                button.textContent = 'Added';
                button.classList.remove('nl-btn--primary');
                button.classList.add('nl-btn--success');
                button.disabled = true;
            }
        });

        document.getElementById('subject').value = template.subject || '';
        document.getElementById('email_header_title').value = template.email_header_title || '';

        updateSelectedItemsDisplay();
        
        setTimeout(() => {
            selectedItems.forEach(item => {
                if ((item.type === 'textblock' || item.type === 'titleblock' || item.type === 'headerblock') && item.content) {
                    setTextBlockContent(item.id, item.content);
                }
            });
            updatePreview();
            if (typeof window.markDraftClean === 'function') window.markDraftClean();
        }, 100);

        console.log('Template loaded:', template.name);
    } catch (error) {
        console.error('Error loading template:', error);
        alert('Error loading template');
    }
}

document.getElementById('delete-template-btn').addEventListener('click', async function() {
    const templateId = this.dataset.templateId;
    if (!templateId) return;
    
    const template = emailTemplates.find(t => t.id == templateId);
    if (!template) return;
    
    if (confirm(`Are you sure you want to delete the template "${template.name}"?`)) {
        try {
            const response = await fetch(`/email_templates/${templateId}`, {
                method: 'DELETE',
                headers: { 'X-CSRF-Token': APP.csrfToken }
            });
            
            const result = await response.json();
            if (result.status === 'success') {
                console.log('Template deleted successfully');
                await loadEmailTemplates();
                
                document.getElementById('template-selector').value = '';
                this.style.display = 'none';
            } else {
                alert('Error deleting template: ' + result.message);
            }
        } catch (error) {
            console.error('Error deleting template:', error);
            alert('Error deleting template');
        }
    }
});

async function blobToDataUri(blob) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = reject;
        reader.readAsDataURL(blob);
    });
}

document.getElementById('export-html-btn').addEventListener('click', async () => {
    const frame = document.getElementById('preview');
    const html = frame?.srcdoc || '';

    if (!html.trim()) {
        alert('Nothing to export, add some snap-ins first.');
        return;
    }

    const subject = document.getElementById('subject')?.value.trim() || 'newsletterr-email';
    const filename = subject.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '') + '.html';

    showSpinner('Embedding images...');
    try {
        // Inline every fetchable image as a base64 data URI so the exported
        // file renders offline. Same-origin assets (proxy-art, uploads, static)
        // fetch with the session cookie; cross-origin or dead links throw and
        // are left as their original URLs.
        const doc = new DOMParser().parseFromString(html, 'text/html');
        await Promise.all(Array.from(doc.querySelectorAll('img')).map(async (img) => {
            const src = img.getAttribute('src') || '';
            if (!src || src.startsWith('data:')) return;
            try {
                const abs = new URL(src, window.location.href).href;
                const resp = await fetch(abs, { credentials: 'same-origin' });
                if (!resp.ok) return;
                img.setAttribute('src', await blobToDataUri(await resp.blob()));
            } catch (_) {
                // cross-origin or unreachable: keep the original URL
            }
        }));

        const finalHtml = '<!DOCTYPE html>\n' + doc.documentElement.outerHTML;
        const blob = new Blob([finalHtml], { type: 'text/html' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        a.click();
        URL.revokeObjectURL(url);
    } catch (err) {
        console.error('Export failed:', err);
        alert('Something went wrong exporting the email.');
    } finally {
        hideSpinner();
    }
});

// PDF export (NEWS-9): same payload as the preview; the server renders via
// the preview pipeline and converts with weasyprint.
document.getElementById('export-pdf-btn').addEventListener('click', async () => {
    const payload = await buildPreviewPayload();
    if (payload === null) {
        alert('Nothing to export, add some snap-ins first.');
        return;
    }

    showSpinner('Rendering PDF...');
    try {
        const resp = await fetch('/export_pdf', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': APP.csrfToken },
            body: JSON.stringify(payload)
        });
        if (!resp.ok) {
            const data = await resp.json().catch(() => ({}));
            throw new Error(data.error || resp.statusText);
        }
        const blob = await resp.blob();

        const subject = document.getElementById('subject')?.value.trim() || 'newsletterr-email';
        const filename = (subject.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '') || 'newsletterr-email') + '.pdf';
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        a.click();
        URL.revokeObjectURL(url);
    } catch (err) {
        console.error('Error exporting PDF:', err);
        alert('PDF export failed: ' + err.message);
    } finally {
        hideSpinner();
    }
});

document.getElementById('import-html-btn').addEventListener('click', () => {
    document.getElementById('import-html-input').click();
});

document.getElementById('import-html-input').addEventListener('change', async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const html = await file.text();
    if (!html.trim()) {
        alert('File appears to be empty.');
        return;
    }

    const templateName = await openSaveTemplateDialog({
        suggestedName: file.name.replace(/\.html?$/i, '')
    });
    if (!templateName) {
        e.target.value = '';
        return;
    }

    const toggle = document.getElementById('custom-html-toggle');
    const editor = document.getElementById('custom-html-editor');
    if (toggle && editor) {
        toggle.checked = true;
        toggle.dispatchEvent(new Event('change'));
        editor.value = html;
        editor.dispatchEvent(new Event('input'));
    }

    try {
        const resp = await fetch('/email_templates', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRF-Token': APP.csrfToken,
            },
            body: JSON.stringify({
                name: templateName.trim(),
                selected_items: '[]',
                email_text: '',
                subject: document.getElementById('subject')?.value || '',
                expanded_collections: '{}',
                header_title: '',
                custom_html: html
            }),
            credentials: 'same-origin'
        });

        const result = await resp.json();
        if (result.status === 'success') {
            await loadEmailTemplates();

            const selector = document.getElementById('template-selector');
            const newTemplate = emailTemplates.find(t => t.name === templateName.trim());
            if (newTemplate) {
                selector.value = newTemplate.id;
                document.getElementById('delete-template-btn').style.display = 'inline-block';
                document.getElementById('delete-template-btn').dataset.templateId = newTemplate.id;
            }
        } else {
            alert('Failed to save template: ' + result.message);
        }
    } catch (err) {
        console.error('Error saving imported template:', err);
        alert('Something went wrong saving the template.');
    }

    e.target.value = '';
});

function showPopoutStatus(message) {
    const statusEl = document.getElementById('popout-status');
    if (!statusEl) return;
    statusEl.textContent = message;
    statusEl.style.display = message ? 'block' : 'none';
    statusEl.style.color = '#f39c12';
}

document.getElementById('popout-preview-btn').addEventListener('click', function() {
    const frame = document.getElementById('preview');
    if (!frame || !frame.srcdoc) {
        alert('No preview content available');
        return;
    }

    if (popoutWindow && !popoutWindow.closed) {
        popoutWindow.focus();
        return;
    }

    // Open at the selected device-size width so the email media queries match
    const popoutWidth = (typeof PREVIEW_SIZES !== 'undefined' ? (PREVIEW_SIZES[currentPreviewSize()] || 800) : 800) + 60;
    popoutWindow = window.open('', 'EmailPreview', `width=${popoutWidth},height=600,scrollbars=yes,resizable=yes`);

    if (popoutWindow) {
        showPopoutStatus('');
        popoutWindow.document.open();
        popoutWindow.document.write(frame.srcdoc);
        popoutWindow.document.close();
        popoutWindow.document.title = 'Email Preview';
        popoutWindow.focus();
    } else {
        showPopoutStatus('Pop-up blocked! Please allow pop-ups for this site to use the preview feature.');
    }
});

document.addEventListener('DOMContentLoaded', () => {
    loadEmailTemplates();
});
