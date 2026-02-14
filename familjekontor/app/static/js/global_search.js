/**
 * Global search (Phase 7A).
 * Debounced AJAX search across all entity types.
 */
(function() {
    var input = document.getElementById('global-search-input');
    var dropdown = document.getElementById('global-search-results');
    if (!input || !dropdown) return;

    var CATEGORY_LABELS = {
        verifications: 'Verifikationer',
        supplier_invoices: 'Leverantörsfakturor',
        customer_invoices: 'Kundfakturor',
        accounts: 'Konton',
        documents: 'Dokument',
        customers: 'Kunder',
        suppliers: 'Leverantörer',
        employees: 'Anställda'
    };

    var debounceTimer = null;
    var activeIndex = -1;

    function getCSRF() {
        var meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute('content') : '';
    }

    function renderResults(data) {
        dropdown.innerHTML = '';
        var keys = Object.keys(data);
        if (keys.length === 0) {
            dropdown.innerHTML = '<div class="px-3 py-2 text-muted small">Inga träffar</div>';
            dropdown.style.display = 'block';
            return;
        }
        keys.forEach(function(cat) {
            var items = data[cat];
            if (!items || items.length === 0) return;
            // Category header
            var header = document.createElement('div');
            header.className = 'search-category';
            header.innerHTML = '<i class="' + items[0].icon + ' me-1"></i>' + (CATEGORY_LABELS[cat] || cat);
            dropdown.appendChild(header);
            // Items
            items.forEach(function(item) {
                var el = document.createElement('a');
                el.href = item.url;
                el.className = 'search-item d-block text-decoration-none text-dark';
                el.innerHTML = '<div class="search-title">' + escapeHtml(item.title) + '</div>' +
                    (item.subtitle ? '<div class="search-subtitle">' + escapeHtml(item.subtitle) + '</div>' : '');
                dropdown.appendChild(el);
            });
        });
        dropdown.style.display = 'block';
        activeIndex = -1;
    }

    function escapeHtml(str) {
        var div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    function doSearch() {
        var q = input.value.trim();
        if (q.length < 2) {
            dropdown.style.display = 'none';
            return;
        }
        fetch('/api/search?q=' + encodeURIComponent(q), {
            headers: { 'X-CSRFToken': getCSRF() }
        })
        .then(function(r) { return r.json(); })
        .then(function(data) {
            renderResults(data.results || {});
        })
        .catch(function() {
            dropdown.style.display = 'none';
        });
    }

    input.addEventListener('input', function() {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(doSearch, 300);
    });

    // Keyboard navigation
    input.addEventListener('keydown', function(e) {
        var items = dropdown.querySelectorAll('.search-item');
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            activeIndex = Math.min(activeIndex + 1, items.length - 1);
            updateActive(items);
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            activeIndex = Math.max(activeIndex - 1, -1);
            updateActive(items);
        } else if (e.key === 'Enter') {
            if (activeIndex >= 0 && items[activeIndex]) {
                e.preventDefault();
                items[activeIndex].click();
            }
        } else if (e.key === 'Escape') {
            dropdown.style.display = 'none';
            input.blur();
        }
    });

    function updateActive(items) {
        items.forEach(function(el, i) {
            el.classList.toggle('active', i === activeIndex);
        });
    }

    // Close on outside click
    document.addEventListener('click', function(e) {
        if (!input.contains(e.target) && !dropdown.contains(e.target)) {
            dropdown.style.display = 'none';
        }
    });

    // Re-show on focus if there's text
    input.addEventListener('focus', function() {
        if (input.value.trim().length >= 2 && dropdown.children.length > 0) {
            dropdown.style.display = 'block';
        }
    });
})();
