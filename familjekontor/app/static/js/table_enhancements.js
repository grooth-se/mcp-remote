/**
 * Table enhancements (Phase 7E)
 * Column visibility toggle with localStorage persistence.
 */
(function() {
  'use strict';

  document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('.col-visibility-dropdown').forEach(initColumnVisibility);
  });

  function initColumnVisibility(dropdown) {
    var table = dropdown.closest('.table-responsive, .batch-container, .card');
    if (!table) table = dropdown.parentElement;
    var tableEl = table.querySelector('table');
    if (!tableEl) return;

    var storageKey = 'col_vis_' + window.location.pathname;
    var menu = dropdown.querySelector('.dropdown-menu');
    var headers = tableEl.querySelectorAll('thead th');

    // Build checkbox items for each column
    headers.forEach(function(th, idx) {
      var text = th.textContent.trim();
      if (!text || text.length < 1) return;  // skip empty/icon-only columns

      var item = document.createElement('li');
      var label = document.createElement('label');
      label.className = 'dropdown-item d-flex align-items-center gap-2';
      var cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.className = 'form-check-input mt-0';
      cb.checked = true;
      cb.dataset.colIdx = idx;
      label.appendChild(cb);
      label.appendChild(document.createTextNode(' ' + text));
      item.appendChild(label);
      menu.appendChild(item);

      cb.addEventListener('change', function() {
        toggleColumn(tableEl, idx, this.checked);
        saveState(storageKey, menu);
      });
    });

    // Restore saved state
    restoreState(storageKey, menu, tableEl);

    // Prevent dropdown from closing on checkbox click
    menu.addEventListener('click', function(e) {
      e.stopPropagation();
    });
  }

  function toggleColumn(table, colIdx, visible) {
    var display = visible ? '' : 'none';
    table.querySelectorAll('tr').forEach(function(row) {
      var cells = row.querySelectorAll('th, td');
      if (cells[colIdx]) {
        cells[colIdx].style.display = display;
      }
    });
  }

  function saveState(key, menu) {
    var state = {};
    menu.querySelectorAll('input[data-col-idx]').forEach(function(cb) {
      state[cb.dataset.colIdx] = cb.checked;
    });
    try { localStorage.setItem(key, JSON.stringify(state)); } catch(e) {}
  }

  function restoreState(key, menu, table) {
    try {
      var saved = localStorage.getItem(key);
      if (!saved) return;
      var state = JSON.parse(saved);
      Object.keys(state).forEach(function(idx) {
        var cb = menu.querySelector('input[data-col-idx="' + idx + '"]');
        if (cb && !state[idx]) {
          cb.checked = false;
          toggleColumn(table, parseInt(idx), false);
        }
      });
    } catch(e) {}
  }
})();
