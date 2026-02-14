/**
 * Notification center (Phase 7B).
 * Bell icon badge, dropdown with recent notifications.
 */
(function() {
    var badge = document.getElementById('notification-count');
    var dropdown = document.getElementById('notification-dropdown');
    var list = document.getElementById('notification-list');
    var markAllBtn = document.getElementById('mark-all-read-btn');
    if (!badge) return;

    function getCSRF() {
        var meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute('content') : '';
    }

    function updateBadge() {
        fetch('/notifications/api/count')
            .then(function(r) { return r.json(); })
            .then(function(data) {
                var c = data.count || 0;
                badge.textContent = c;
                if (c > 0) {
                    badge.classList.remove('d-none');
                } else {
                    badge.classList.add('d-none');
                }
            })
            .catch(function() {});
    }

    function loadRecent() {
        fetch('/notifications/api/recent')
            .then(function(r) { return r.json(); })
            .then(function(data) {
                var notifs = data.notifications || [];
                if (notifs.length === 0) {
                    list.innerHTML = '<div class="text-center py-3 text-muted small">Inga aviseringar</div>';
                    return;
                }
                var html = '';
                notifs.forEach(function(n) {
                    var cls = n.read ? 'notification-item' : 'notification-item unread';
                    html += '<a href="#" class="' + cls + ' d-block text-decoration-none text-dark" ' +
                        'data-id="' + n.id + '" data-link="' + escapeAttr(n.link) + '">' +
                        '<div class="d-flex align-items-start">' +
                        '<i class="' + n.icon + ' me-2 mt-1"></i>' +
                        '<div class="flex-grow-1">' +
                        '<div class="fw-semibold small">' + escapeHtml(n.title) + '</div>' +
                        (n.message ? '<div class="text-muted" style="font-size:0.8rem;">' + escapeHtml(n.message) + '</div>' : '') +
                        '<div class="notification-time">' + n.created_at + '</div>' +
                        '</div></div></a>';
                });
                list.innerHTML = html;

                // Click handler for each notification
                list.querySelectorAll('.notification-item').forEach(function(el) {
                    el.addEventListener('click', function(e) {
                        e.preventDefault();
                        e.stopPropagation();
                        var id = el.getAttribute('data-id');
                        var link = el.getAttribute('data-link');
                        // Mark as read
                        fetch('/notifications/' + id + '/read', {
                            method: 'POST',
                            headers: { 'X-CSRFToken': getCSRF(), 'Content-Type': 'application/json' },
                        }).then(function() {
                            if (link) window.location.href = link;
                        }).catch(function() {
                            if (link) window.location.href = link;
                        });
                    });
                });
            })
            .catch(function() {
                list.innerHTML = '<div class="text-center py-3 text-muted small">Kunde inte ladda</div>';
            });
    }

    function escapeHtml(str) {
        var div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    function escapeAttr(str) {
        return str ? str.replace(/"/g, '&quot;').replace(/'/g, '&#39;') : '';
    }

    // Load count on page load
    updateBadge();

    // Load recent when dropdown opens
    if (dropdown) {
        var bellToggle = document.querySelector('#notification-bell > a');
        if (bellToggle) {
            bellToggle.addEventListener('click', function() {
                loadRecent();
            });
        }
    }

    // Mark all read button
    if (markAllBtn) {
        markAllBtn.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            fetch('/notifications/mark-all-read', {
                method: 'POST',
                headers: { 'X-CSRFToken': getCSRF(), 'Content-Type': 'application/json' },
            }).then(function() {
                updateBadge();
                loadRecent();
            }).catch(function() {});
        });
    }

    // Poll every 60 seconds
    setInterval(updateBadge, 60000);
})();
