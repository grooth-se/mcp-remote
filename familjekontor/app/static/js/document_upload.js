// Document drag-and-drop upload

document.addEventListener('DOMContentLoaded', function() {
    const dropZone = document.getElementById('dropZone');
    const dropResult = document.getElementById('dropResult');
    if (!dropZone) return;

    const csrfToken = document.querySelector('input[name="csrf_token"]')?.value || '';

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
        const files = e.dataTransfer.files;
        if (files.length === 0) return;

        for (let i = 0; i < files.length; i++) {
            uploadFile(files[i]);
        }
    });

    function uploadFile(file) {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('document_type', 'ovrigt');
        formData.append('csrf_token', csrfToken);

        const statusDiv = document.createElement('div');
        statusDiv.className = 'alert alert-info';
        statusDiv.textContent = 'Laddar upp ' + file.name + '...';
        dropResult.appendChild(statusDiv);

        fetch('/documents/api/upload', {
            method: 'POST',
            body: formData,
        })
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (data.success) {
                statusDiv.className = 'alert alert-success';
                statusDiv.innerHTML = '<i class="bi bi-check-circle"></i> ' + data.file_name +
                    ' - <a href="' + data.url + '">Visa</a>';
            } else {
                statusDiv.className = 'alert alert-danger';
                statusDiv.textContent = 'Fel: ' + (data.error || 'Okant fel');
            }
        })
        .catch(function(err) {
            statusDiv.className = 'alert alert-danger';
            statusDiv.textContent = 'Natverksfel: ' + err.message;
        });
    }
});
