document.getElementById('media-upload-input').addEventListener('change', async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const targetIndex = e.target.dataset.targetIndex !== undefined 
        ? parseInt(e.target.dataset.targetIndex) 
        : null;

    const formData = new FormData();
    formData.append('file', file);
    formData.append('csrf_token', APP.csrfToken);

    showSpinner('Uploading media...');
    try {
        const resp = await fetch('/upload/media', { method: 'POST', body: formData, credentials: 'same-origin' });
        const result = await resp.json();
        if (result.status === 'success') {
            if (targetIndex !== null && selectedItems[targetIndex]) {
                selectedItems[targetIndex].src = result.url;
                selectedItems[targetIndex].isUpload = true;
                updateSelectedItemsDisplay();
                debouncedUpdatePreview();
            } else {
                createImageBlock(result.url, true);
            }
        } else {
            alert('Upload failed: ' + result.message);
        }
    } catch (err) {
        console.error('Upload error:', err);
        alert('Something went wrong uploading the file.');
    } finally {
        hideSpinner();
        e.target.value = '';
        delete e.target.dataset.targetIndex;
    }
});
