// Document drag-and-drop upload — two-step flow with staging area

document.addEventListener('DOMContentLoaded', function() {
    var dropZone = document.getElementById('dropZone');
    var stagingArea = document.getElementById('stagingArea');
    if (!dropZone || !stagingArea) return;

    var csrfToken = document.getElementById('csrfToken')?.value
        || document.querySelector('input[name="csrf_token"]')?.value || '';
    var fileCounter = 0;

    var typeLabels = {
        'faktura': 'Faktura',
        'avtal': 'Avtal',
        'intyg': 'Intyg',
        'certificate': 'Registreringsdokument',
        'arsredovisning': 'Årsredovisning',
        'kvitto': 'Kvitto',
        'ovrigt': 'Övrigt'
    };

    ['dragenter', 'dragover'].forEach(function(event) {
        dropZone.addEventListener(event, function(e) {
            e.preventDefault();
            dropZone.classList.add('dragover');
        });
    });

    ['dragleave', 'drop'].forEach(function(event) {
        dropZone.addEventListener(event, function(e) {
            e.preventDefault();
            dropZone.classList.remove('dragover');
        });
    });

    dropZone.addEventListener('drop', function(e) {
        var files = e.dataTransfer.files;
        if (files.length === 0) return;
        for (var i = 0; i < files.length; i++) {
            stageFile(files[i]);
        }
    });

    // Also allow click to select files
    dropZone.addEventListener('click', function() {
        var input = document.createElement('input');
        input.type = 'file';
        input.multiple = true;
        input.accept = '.pdf,.png,.jpg,.jpeg,.gif,.doc,.docx,.xls,.xlsx,.csv,.txt';
        input.addEventListener('change', function() {
            for (var i = 0; i < input.files.length; i++) {
                stageFile(input.files[i]);
            }
        });
        input.click();
    });

    function stageFile(file) {
        fileCounter++;
        var id = 'staged-' + fileCounter;

        var card = document.createElement('div');
        card.className = 'card mb-3';
        card.id = id;
        card.dataset.fileRef = fileCounter;
        card.innerHTML = buildStagingCard(id, file.name);
        stagingArea.appendChild(card);

        // Store file reference on the card
        card._file = file;

        // Show loading state
        var statusEl = card.querySelector('.stage-status');
        statusEl.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Analyserar...';

        // Call analyze endpoint
        var formData = new FormData();
        formData.append('file', file);
        formData.append('csrf_token', csrfToken);

        fetch('/documents/api/analyze', {
            method: 'POST',
            body: formData
        })
        .then(function(r) {
            if (!r.ok) {
                console.error('Analyze API error:', r.status, r.statusText);
                return r.text().then(function(t) { throw new Error('HTTP ' + r.status + ': ' + t.substring(0, 200)); });
            }
            return r.json();
        })
        .then(function(data) {
            statusEl.innerHTML = '<i class="bi bi-check-circle text-success"></i> Analys klar';
            // Fill in suggestions
            if (data.suggested_type) {
                card.querySelector('.stage-type').value = data.suggested_type;
            }
            if (data.suggested_description) {
                card.querySelector('.stage-description').value = data.suggested_description;
            }
            if (data.suggested_valid_from) {
                card.querySelector('.stage-valid-from').value = data.suggested_valid_from;
            }
            if (data.suggested_expiry_date) {
                card.querySelector('.stage-expiry-date').value = data.suggested_expiry_date;
            }
            // Enable upload button
            card.querySelector('.btn-upload').disabled = false;
        })
        .catch(function(err) {
            statusEl.innerHTML = '<i class="bi bi-exclamation-triangle text-warning"></i> Analys misslyckades';
            // Still allow manual upload
            card.querySelector('.btn-upload').disabled = false;
        });

        updateUploadAllButton();
    }

    function buildStagingCard(id, filename) {
        var typeOptions = '';
        for (var key in typeLabels) {
            typeOptions += '<option value="' + key + '">' + typeLabels[key] + '</option>';
        }

        return '<div class="card-body">' +
            '<div class="d-flex justify-content-between align-items-start mb-2">' +
                '<div>' +
                    '<i class="bi bi-file-earmark me-1"></i>' +
                    '<strong>' + escapeHtml(filename) + '</strong>' +
                    ' <span class="stage-status text-muted small"></span>' +
                '</div>' +
                '<button type="button" class="btn-close btn-sm" onclick="this.closest(\'.card\').remove(); updateUploadAllButton();" aria-label="Ta bort"></button>' +
            '</div>' +
            '<div class="row g-2">' +
                '<div class="col-md-3">' +
                    '<label class="form-label small">Dokumenttyp</label>' +
                    '<select class="form-select form-select-sm stage-type">' + typeOptions + '</select>' +
                '</div>' +
                '<div class="col-md-3">' +
                    '<label class="form-label small">Beskrivning</label>' +
                    '<input type="text" class="form-control form-control-sm stage-description" placeholder="Valfri beskrivning">' +
                '</div>' +
                '<div class="col-md-2">' +
                    '<label class="form-label small">Giltig från</label>' +
                    '<input type="date" class="form-control form-control-sm stage-valid-from">' +
                '</div>' +
                '<div class="col-md-2">' +
                    '<label class="form-label small">Giltig till</label>' +
                    '<input type="date" class="form-control form-control-sm stage-expiry-date">' +
                '</div>' +
                '<div class="col-md-2 d-flex align-items-end">' +
                    '<button type="button" class="btn btn-sm btn-primary w-100 btn-upload" disabled onclick="uploadStagedFile(this)"><i class="bi bi-upload"></i> Ladda upp</button>' +
                '</div>' +
            '</div>' +
        '</div>';
    }

    function escapeHtml(text) {
        var div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // Make uploadStagedFile global
    window.uploadStagedFile = function(btn) {
        var card = btn.closest('.card');
        var file = card._file;
        if (!file) return;

        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';

        var formData = new FormData();
        formData.append('file', file);
        formData.append('document_type', card.querySelector('.stage-type').value);
        formData.append('description', card.querySelector('.stage-description').value);
        formData.append('valid_from', card.querySelector('.stage-valid-from').value);
        formData.append('expiry_date', card.querySelector('.stage-expiry-date').value);
        formData.append('csrf_token', csrfToken);

        fetch('/documents/api/upload', {
            method: 'POST',
            body: formData
        })
        .then(function(r) {
            if (!r.ok) {
                console.error('Upload API error:', r.status, r.statusText);
            }
            return r.json();
        })
        .then(function(data) {
            if (data.success) {
                card.className = 'card mb-3 border-success';
                card.querySelector('.card-body').innerHTML =
                    '<div class="d-flex justify-content-between align-items-center">' +
                        '<span><i class="bi bi-check-circle text-success me-1"></i> ' +
                        '<strong>' + escapeHtml(data.file_name) + '</strong> uppladdad</span>' +
                        '<a href="' + data.url + '" class="btn btn-sm btn-outline-success">Visa</a>' +
                    '</div>';
            } else {
                btn.disabled = false;
                btn.innerHTML = '<i class="bi bi-upload"></i> Ladda upp';
                var statusEl = card.querySelector('.stage-status');
                if (statusEl) {
                    statusEl.innerHTML = '<span class="text-danger">Fel: ' + (data.error || 'Okänt fel') + '</span>';
                }
            }
        })
        .catch(function(err) {
            btn.disabled = false;
            btn.innerHTML = '<i class="bi bi-upload"></i> Ladda upp';
            var statusEl = card.querySelector('.stage-status');
            if (statusEl) {
                statusEl.innerHTML = '<span class="text-danger">Nätverksfel: ' + err.message + '</span>';
            }
        });
    };

    // Upload all staged files
    window.uploadAllStaged = function() {
        var buttons = stagingArea.querySelectorAll('.btn-upload:not([disabled])');
        buttons.forEach(function(btn) {
            // Only upload if not already uploaded (card not success)
            if (!btn.closest('.card').classList.contains('border-success')) {
                window.uploadStagedFile(btn);
            }
        });
    };

    window.updateUploadAllButton = function() {
        var uploadAllBtn = document.getElementById('uploadAllBtn');
        if (!uploadAllBtn) return;
        var pending = stagingArea.querySelectorAll('.card:not(.border-success)');
        uploadAllBtn.style.display = pending.length > 1 ? 'inline-block' : 'none';
    };
});
