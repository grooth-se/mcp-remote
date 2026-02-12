// Budget Grid Editor - save via fetch

function updateRowTotals() {
    document.querySelectorAll('#budgetGrid tbody tr').forEach(function(row) {
        let total = 0;
        row.querySelectorAll('.budget-input').forEach(function(input) {
            total += parseFloat(input.value) || 0;
        });
        const totalCell = row.querySelector('.row-total');
        if (totalCell) {
            totalCell.textContent = total.toLocaleString('sv-SE', {maximumFractionDigits: 0});
        }
    });
}

function saveBudget() {
    const grid = {};
    document.querySelectorAll('.budget-input').forEach(function(input) {
        const accountId = input.dataset.account;
        const month = input.dataset.month;
        const value = input.value || '0';

        if (!grid[accountId]) grid[accountId] = {};
        grid[accountId][month] = value;
    });

    // Get fiscal year ID from URL
    const urlParams = new URLSearchParams(window.location.search);
    const fyId = urlParams.get('fiscal_year_id');

    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content ||
                      document.querySelector('input[name="csrf_token"]')?.value || '';

    // Loading state on save button
    const saveBtn = document.getElementById('saveBtn');
    if (saveBtn) {
        saveBtn.disabled = true;
        saveBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status"></span> Sparar...';
    }

    fetch('/budget/api/save-grid', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken,
        },
        body: JSON.stringify({
            fiscal_year_id: parseInt(fyId),
            grid: grid,
        }),
    })
    .then(r => r.json())
    .then(data => {
        const status = document.getElementById('saveStatus');
        if (data.success) {
            status.textContent = 'Budget sparad! (' + data.updated + ' rader uppdaterade)';
            status.className = 'alert alert-success mb-3';
        } else {
            status.textContent = 'Fel: ' + (data.error || 'Okant fel');
            status.className = 'alert alert-danger mb-3';
        }
        status.classList.remove('d-none');
        setTimeout(() => status.classList.add('d-none'), 3000);
        if (saveBtn) {
            saveBtn.disabled = false;
            saveBtn.innerHTML = '<i class="bi bi-save"></i> Spara';
        }
    })
    .catch(err => {
        const status = document.getElementById('saveStatus');
        status.textContent = 'Natverksfel: ' + err.message;
        status.className = 'alert alert-danger mb-3';
        status.classList.remove('d-none');
        if (saveBtn) {
            saveBtn.disabled = false;
            saveBtn.innerHTML = '<i class="bi bi-save"></i> Spara';
        }
    });
}

// Update totals on input change
document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('.budget-input').forEach(function(input) {
        input.addEventListener('change', updateRowTotals);
        input.addEventListener('input', updateRowTotals);
    });
});
