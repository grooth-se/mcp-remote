/* Durabler Web Application JavaScript */

// File upload drag and drop
document.addEventListener('DOMContentLoaded', function() {
    const uploadAreas = document.querySelectorAll('.upload-area');

    uploadAreas.forEach(area => {
        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
            area.addEventListener(eventName, preventDefaults, false);
        });

        ['dragenter', 'dragover'].forEach(eventName => {
            area.addEventListener(eventName, () => area.classList.add('dragover'), false);
        });

        ['dragleave', 'drop'].forEach(eventName => {
            area.addEventListener(eventName, () => area.classList.remove('dragover'), false);
        });

        area.addEventListener('drop', handleDrop, false);
    });
});

function preventDefaults(e) {
    e.preventDefault();
    e.stopPropagation();
}

function handleDrop(e) {
    const dt = e.dataTransfer;
    const files = dt.files;
    const fileInput = e.target.querySelector('input[type="file"]');

    if (fileInput && files.length > 0) {
        fileInput.files = files;
        // Trigger change event
        fileInput.dispatchEvent(new Event('change'));
    }
}

// Confirm delete actions
function confirmDelete(message) {
    return confirm(message || 'Are you sure you want to delete this item?');
}

// Format numbers with uncertainty
function formatWithUncertainty(value, uncertainty, decimals = 2) {
    if (uncertainty === null || uncertainty === undefined) {
        return value.toFixed(decimals);
    }
    return `${value.toFixed(decimals)} ± ${uncertainty.toFixed(decimals)}`;
}

// Auto-dismiss alerts after 5 seconds
document.addEventListener('DOMContentLoaded', function() {
    const alerts = document.querySelectorAll('.alert-dismissible');
    alerts.forEach(alert => {
        setTimeout(() => {
            const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
            bsAlert.close();
        }, 5000);
    });
});

console.log('Durabler Web Application loaded');
