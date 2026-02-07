// Verification form - dynamic rows and balance calculation

let rowCount = 2;

function addRow() {
    const tbody = document.getElementById('rowsBody');
    const firstRow = tbody.querySelector('.ver-row');
    const selectHtml = firstRow.querySelector('select').innerHTML;

    const idx = rowCount;
    const tr = document.createElement('tr');
    tr.className = 'ver-row';
    tr.dataset.index = idx;
    tr.innerHTML = `
        <td>
            <select name="rows-${idx}-account_id" class="form-select form-select-sm">
                ${selectHtml}
            </select>
        </td>
        <td><input type="number" step="0.01" name="rows-${idx}-debit" class="form-control form-control-sm debit-input" value="0"></td>
        <td><input type="number" step="0.01" name="rows-${idx}-credit" class="form-control form-control-sm credit-input" value="0"></td>
        <td><input type="text" name="rows-${idx}-description" class="form-control form-control-sm"></td>
        <td><button type="button" class="btn btn-sm btn-outline-danger" onclick="removeRow(this)"><i class="bi bi-trash"></i></button></td>
    `;
    tbody.appendChild(tr);
    rowCount++;

    // Add event listeners
    tr.querySelectorAll('.debit-input, .credit-input').forEach(input => {
        input.addEventListener('input', updateTotals);
    });
}

function removeRow(btn) {
    const tbody = document.getElementById('rowsBody');
    if (tbody.querySelectorAll('.ver-row').length > 1) {
        btn.closest('tr').remove();
        updateTotals();
    }
}

function updateTotals() {
    let totalDebit = 0;
    let totalCredit = 0;

    document.querySelectorAll('.debit-input').forEach(input => {
        totalDebit += parseFloat(input.value) || 0;
    });
    document.querySelectorAll('.credit-input').forEach(input => {
        totalCredit += parseFloat(input.value) || 0;
    });

    document.getElementById('totalDebit').textContent = totalDebit.toFixed(2);
    document.getElementById('totalCredit').textContent = totalCredit.toFixed(2);

    const status = document.getElementById('balanceStatus');
    const diff = Math.abs(totalDebit - totalCredit);
    if (diff < 0.01 && (totalDebit > 0 || totalCredit > 0)) {
        status.textContent = 'Balanserad';
        status.className = 'badge balanced';
    } else if (totalDebit > 0 || totalCredit > 0) {
        status.textContent = `Differens: ${diff.toFixed(2)}`;
        status.className = 'badge unbalanced';
    } else {
        status.textContent = '-';
        status.className = 'badge bg-secondary';
    }
}

// Initialize
document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('.debit-input, .credit-input').forEach(input => {
        input.addEventListener('input', updateTotals);
    });
    updateTotals();
});
