/**
 * Batch Operations (Phase 7C)
 * Handles select-all, count badge, toolbar visibility, and batch actions.
 */
(function() {
  'use strict';

  document.addEventListener('DOMContentLoaded', function() {
    var toolbar = document.getElementById('batch-toolbar');
    if (!toolbar) return;

    var selectAll = document.getElementById('batch-select-all');
    var countBadge = document.getElementById('batch-count');
    var table = toolbar.closest('.batch-container') || toolbar.parentElement;
    var csrfToken = document.querySelector('meta[name="csrf-token"]');
    var csrf = csrfToken ? csrfToken.getAttribute('content') : '';

    function getCheckboxes() {
      return table.querySelectorAll('.batch-checkbox');
    }

    function getSelectedIds() {
      var ids = [];
      getCheckboxes().forEach(function(cb) {
        if (cb.checked) ids.push(cb.value);
      });
      return ids;
    }

    function updateToolbar() {
      var ids = getSelectedIds();
      var count = ids.length;
      if (countBadge) countBadge.textContent = count;
      toolbar.style.display = count > 0 ? '' : 'none';

      // Update select-all state
      var boxes = getCheckboxes();
      if (selectAll && boxes.length > 0) {
        var allChecked = true;
        boxes.forEach(function(cb) { if (!cb.checked) allChecked = false; });
        selectAll.checked = allChecked;
        selectAll.indeterminate = count > 0 && !allChecked;
      }
    }

    // Select-all toggle
    if (selectAll) {
      selectAll.addEventListener('change', function() {
        var checked = this.checked;
        getCheckboxes().forEach(function(cb) {
          cb.checked = checked;
        });
        updateToolbar();
      });
    }

    // Individual checkbox changes
    table.addEventListener('change', function(e) {
      if (e.target.classList.contains('batch-checkbox')) {
        updateToolbar();
      }
    });

    // Prevent row-click navigation when clicking checkboxes
    table.addEventListener('click', function(e) {
      if (e.target.classList.contains('batch-checkbox') || e.target.closest('.batch-check-cell')) {
        e.stopPropagation();
      }
    });

    // Batch action buttons
    toolbar.querySelectorAll('[data-batch-action]').forEach(function(btn) {
      btn.addEventListener('click', function(e) {
        e.preventDefault();
        var ids = getSelectedIds();
        if (ids.length === 0) return;

        var action = this.getAttribute('data-batch-action');
        var url = this.getAttribute('data-batch-url');
        var confirmMsg = this.getAttribute('data-batch-confirm');

        if (confirmMsg && !confirm(confirmMsg)) return;

        // Create and submit hidden form
        var form = document.createElement('form');
        form.method = 'POST';
        form.action = url;
        form.style.display = 'none';

        var csrfInput = document.createElement('input');
        csrfInput.type = 'hidden';
        csrfInput.name = 'csrf_token';
        csrfInput.value = csrf;
        form.appendChild(csrfInput);

        var idsInput = document.createElement('input');
        idsInput.type = 'hidden';
        idsInput.name = 'ids';
        idsInput.value = ids.join(',');
        form.appendChild(idsInput);

        document.body.appendChild(form);
        form.submit();
      });
    });

    // Initial state
    updateToolbar();
  });
})();
