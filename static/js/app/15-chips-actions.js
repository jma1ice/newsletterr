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
        
        const chip = document.createElement('span');
        chip.className = 'nl-chip';
        chip.dataset.email = email;
        chip.innerHTML = `
            <span>${email}</span>
            <button type="button" class="remove" aria-label="Remove ${email}">x</button>
        `;
        bccChipsContainer.insertBefore(chip, emailInput);
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
    
    selector.addEventListener('change', async () => {
        const selectedValue = selector.value;
        
        deleteBtn.classList.add('d-none');
        saveContainer.classList.add('d-none');
        
        if (selectedValue === 'Custom') {
            setReadOnlyMode(false);
        } else if (selectedValue === 'ALL') {
            clearAllChips();
            allUserEmails.forEach(email => addEmailChip(email));
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
                emails.split(', ').forEach(email => addEmailChip(email.trim()));
                deleteBtn.classList.remove('d-none');
                setReadOnlyMode(false);
            }
        }
    });
    
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
                method: 'DELETE'
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
