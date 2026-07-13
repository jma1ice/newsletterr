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

document.getElementById('template-selector').addEventListener('change', async function() {
    const value = this.value;
    const deleteBtn = document.getElementById('delete-template-btn');
    
    if (value === 'save-template') {
        const templateName = prompt('Enter template name:');
        if (templateName && templateName.trim()) {
            await saveCurrentTemplate(templateName.trim());
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
        
        document.querySelectorAll('.add-stat-btn, .add-graph-btn, .ra-add-btn, .recs-add-btn, .droppedneedle-add-btn, .droppedneedle-server-add-btn, .yearly-wrapped-add-btn, .sonarr-coming-soon-add-btn, .radarr-coming-soon-add-btn').forEach(btn => {
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
    }
});

async function saveCurrentTemplate(name) {
    try {
        const _sentinelContent = (item) => {
            const raw = getTextBlockContent(item.id) || '';
            if (item.id.startsWith('intro-block-') && raw === _resolvedIntroDefault) return '__DEFAULT_INTRO__';
            if (item.id.startsWith('outro-block-') && raw === _resolvedOutroDefault) return '__DEFAULT_OUTRO__';
            return raw;
        };

        const textBlocks = selectedItems
            .filter(item => item.type === 'textblock' || item.type === 'titleblock' || item.type === 'headerblock')
            .map(item => _sentinelContent(item))
            .filter(content => content.trim().length > 0);

        const itemsWithContent = selectedItems.map(item => {
            if (item.type === 'textblock' || item.type === 'titleblock' || item.type === 'headerblock') {
                return { ...item, content: _sentinelContent(item) };
            }
            return item;
        });

        const expandedCollections = window.expandedCollections || {};
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
        
        document.querySelectorAll('.add-stat-btn, .add-graph-btn, .ra-add-btn, .recs-add-btn, .droppedneedle-add-btn, .droppedneedle-server-add-btn, .yearly-wrapped-add-btn, .sonarr-coming-soon-add-btn, .radarr-coming-soon-add-btn').forEach(btn => {
            btn.textContent = 'Add';
            btn.classList.remove('nl-btn--success');
            btn.classList.add('nl-btn--primary');
            btn.disabled = false;
        });
        
        selectedItems = items.map(item => {
            if ((item.type === 'textblock' || item.type === 'titleblock' || item.type === 'headerblock') && item.content) {
                if (item.type === 'textblock' && item.id.startsWith('text-block-')) {
                    const counter = parseInt(item.id.split('-')[2]);
                    if (counter >= textBlockCounter) {
                        textBlockCounter = counter;
                    }
                } else if (item.type === 'titleblock' && item.id.startsWith('title-block-')) {
                    const counter = parseInt(item.id.split('-')[2]);
                    if (counter >= titleBlockCounter) {
                        titleBlockCounter = counter;
                    }
                } else if (item.type === 'headerblock' && item.id.startsWith('header-block-')) {
                    const counter = parseInt(item.id.split('-')[2]);
                    if (counter >= headerBlockCounter) {
                        headerBlockCounter = counter;
                    }
                } else if (item.type === 'textblock' && item.id.startsWith('intro-block-')) {
                    const counter = parseInt(item.id.split('-')[2]);
                    if (counter >= textBlockCounter) {
                        textBlockCounter = counter;
                    }
                } else if (item.type === 'textblock' && item.id.startsWith('outro-block-')) {
                    const counter = parseInt(item.id.split('-')[2]);
                    if (counter >= textBlockCounter) {
                        textBlockCounter = counter;
                    }
                }
            }
            return { ...item };
        });

        if (template.expanded_collections) {
            try {
                const expandedCollections = JSON.parse(template.expanded_collections);
                window.expandedCollections = expandedCollections;
                console.log('Restored expansion state from template:', expandedCollections);
                window.collapsedCollectionsUI = {};
            } catch (e) {
                console.warn('Failed to parse expanded collections from template:', e);
                window.expandedCollections = {};
                window.collapsedCollectionsUI = {};
            }
        } else {
            window.expandedCollections = {};
        }
        
        selectedItems.forEach(item => {
            if (item.type === 'graph' && !renderedCharts.has(item.id)) {
                try {
                    const index = parseInt(item.id.split('-')[1]);
                    const graphData = graphDataList[index];

                    if (graphData && graphCommands[index]) {
                        Highcharts.chart(item.id, {
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

                        renderedCharts.add(item.id);
                        
                        const nowDark = document.documentElement.classList.contains('dark');
                        applyChartTheme(nowDark);
                        
                        console.log('Auto-rendered graph during template load:', item.id);
                    }
                } catch (error) {
                    console.warn('Failed to auto-render graph during template load', item.id, error);
                }
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
                    let content = item.content;
                    if (content === '__DEFAULT_INTRO__') content = _resolvedIntroDefault;
                    else if (content === '__DEFAULT_OUTRO__') content = _resolvedOutroDefault;
                    setTextBlockContent(item.id, content);
                }
            });
            updatePreview();
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

document.getElementById('export-html-btn').addEventListener('click', () => {
    const frame = document.getElementById('preview');
    const html = frame?.srcdoc || '';

    if (!html.trim()) {
        alert('Nothing to export, add some snap-ins first.');
        return;
    }

    const subject = document.getElementById('subject')?.value.trim() || 'newsletterr-email';
    const filename = subject.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '') + '.html';

    const blob = new Blob([html], { type: 'text/html' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
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

    const templateName = prompt('Enter a name for this template:', file.name.replace('.html', ''));
    if (!templateName?.trim()) {
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

    popoutWindow = window.open('', 'EmailPreview', 'width=800,height=600,scrollbars=yes,resizable=yes');

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
