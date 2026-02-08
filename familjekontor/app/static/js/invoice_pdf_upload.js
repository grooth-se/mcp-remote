// Invoice PDF upload — drag-and-drop with auto-populate form fields

document.addEventListener('DOMContentLoaded', function() {
    var dropZone = document.getElementById('invoiceDropZone');
    var form = document.getElementById('invoiceForm');
    if (!dropZone || !form) return;

    // Prevent browser from opening files dropped anywhere on the page
    ['dragenter', 'dragover', 'drop'].forEach(function(event) {
        window.addEventListener(event, function(e) {
            e.preventDefault();
        });
    });

    var csrfToken = document.getElementById('csrfToken')?.value
        || document.querySelector('input[name="csrf_token"]')?.value || '';
    var stagedFile = null;

    // Drop zone visual feedback
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

    // Handle drop
    dropZone.addEventListener('drop', function(e) {
        var files = e.dataTransfer.files;
        if (files.length > 0) {
            analyzeInvoice(files[0]);
        }
    });

    // Handle click to select
    dropZone.addEventListener('click', function() {
        var input = document.createElement('input');
        input.type = 'file';
        input.accept = '.pdf';
        input.addEventListener('change', function() {
            if (input.files.length > 0) {
                analyzeInvoice(input.files[0]);
            }
        });
        input.click();
    });

    function analyzeInvoice(file) {
        stagedFile = file;

        // Update drop zone to show file name
        dropZone.innerHTML =
            '<i class="bi bi-file-earmark-pdf fs-1 text-success"></i>' +
            '<p class="mt-2 mb-0"><strong>' + escapeHtml(file.name) + '</strong></p>' +
            '<small class="text-muted">Klicka eller dra en ny fil för att byta</small>';

        var status = document.getElementById('analyzeStatus');
        status.style.display = 'block';
        status.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Analyserar faktura...';

        var fd = new FormData();
        fd.append('file', file);
        fd.append('csrf_token', csrfToken);

        fetch('/invoices/api/analyze-invoice-pdf', {
            method: 'POST',
            body: fd
        })
        .then(function(r) {
            if (!r.ok) {
                console.error('Analyze API error:', r.status);
                throw new Error('HTTP ' + r.status);
            }
            return r.json();
        })
        .then(function(data) {
            status.innerHTML = '<i class="bi bi-check-circle text-success me-1"></i> Analys klar — granska fälten nedan';
            populateForm(data);
        })
        .catch(function(err) {
            status.innerHTML = '<i class="bi bi-exclamation-triangle text-warning me-1"></i> Kunde inte analysera PDF — fyll i manuellt';
            console.error('Invoice analyze error:', err);
        });
    }

    function populateForm(data) {
        if (data.invoice_number) setField('invoice_number', data.invoice_number);
        if (data.invoice_date) setField('invoice_date', data.invoice_date);
        if (data.due_date) setField('due_date', data.due_date);
        if (data.amount_excl_vat) setField('amount_excl_vat', data.amount_excl_vat);
        if (data.vat_amount) setField('vat_amount', data.vat_amount);
        if (data.total_amount) setField('total_amount', data.total_amount);
        if (data.supplier_id) {
            var sel = document.getElementById('supplier_id');
            if (sel) {
                sel.value = data.supplier_id;
                sel.classList.add('border-success');
            }
        }
        if (data.currency) {
            var cur = document.getElementById('currency');
            if (cur) {
                cur.value = data.currency;
                cur.classList.add('border-success');
            }
        }
    }

    function setField(fieldId, value) {
        var el = document.getElementById(fieldId);
        if (el && !el.value) {
            el.value = value;
            el.classList.add('border-success');
        }
    }

    function escapeHtml(text) {
        var div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // Intercept form submit to include the staged PDF file
    form.addEventListener('submit', function(e) {
        if (stagedFile) {
            e.preventDefault();

            var fd = new FormData(form);
            fd.append('invoice_pdf', stagedFile);

            fetch(form.action || window.location.href, {
                method: 'POST',
                body: fd,
                redirect: 'follow'
            })
            .then(function(r) {
                // Follow the redirect
                if (r.redirected) {
                    window.location.href = r.url;
                } else {
                    return r.text().then(function(html) {
                        document.open();
                        document.write(html);
                        document.close();
                    });
                }
            })
            .catch(function(err) {
                console.error('Submit error:', err);
                alert('Fel vid sparande: ' + err.message);
            });
        }
        // If no staged file, normal form submit proceeds
    });
});
