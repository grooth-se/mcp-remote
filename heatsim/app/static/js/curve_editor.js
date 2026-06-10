/*
 * Table editor for temperature-dependent material property curves.
 *
 * Rows are serialized into the hidden #curve_data field as
 * {"temperature": [...], "value": [...]} on submit, so the server-side
 * contract is identical to the old JSON textarea. Supports pasting two
 * columns straight from Excel (tab- or semicolon-separated) and decimal
 * commas.
 */
document.addEventListener('DOMContentLoaded', function () {
    const hiddenField = document.getElementById('curve_data');
    const table = document.getElementById('curveTable');
    if (!hiddenField || !table) return;

    const tbody = table.querySelector('tbody');
    const errorsDiv = document.getElementById('curveErrors');
    const addRowBtn = document.getElementById('curveAddRow');
    const form = hiddenField.closest('form');
    const propertyType = document.getElementById('property_type');

    function parseCell(text) {
        let t = String(text == null ? '' : text).trim();
        if (t === '') return null;
        if (t.includes(',') && !t.includes('.') && t.split(',').length === 2) {
            t = t.replace(',', '.');
        }
        const v = Number(t);
        return Number.isFinite(v) ? v : null;
    }

    function addRow(temp, value) {
        const tr = document.createElement('tr');
        tr.innerHTML =
            '<td><input type="text" inputmode="decimal" class="form-control form-control-sm curve-temp"></td>' +
            '<td><input type="text" inputmode="decimal" class="form-control form-control-sm curve-value"></td>' +
            '<td><button type="button" class="btn btn-sm btn-outline-danger curve-remove" title="Remove row">' +
            '<i class="bi bi-x-lg"></i></button></td>';
        if (temp !== undefined && temp !== null) tr.querySelector('.curve-temp').value = temp;
        if (value !== undefined && value !== null) tr.querySelector('.curve-value').value = value;
        tr.querySelector('.curve-remove').addEventListener('click', function () {
            tr.remove();
            if (!tbody.children.length) addRow();
        });
        tbody.appendChild(tr);
        return tr;
    }

    function collectRows() {
        const temps = [];
        const values = [];
        let badRows = 0;
        tbody.querySelectorAll('tr').forEach(function (tr) {
            const tRaw = tr.querySelector('.curve-temp').value.trim();
            const vRaw = tr.querySelector('.curve-value').value.trim();
            if (tRaw === '' && vRaw === '') return; // skip fully empty rows
            const t = parseCell(tRaw);
            const v = parseCell(vRaw);
            if (t === null || v === null) {
                badRows += 1;
                return;
            }
            temps.push(t);
            values.push(v);
        });
        return { temps: temps, values: values, badRows: badRows };
    }

    function clearRows() {
        tbody.innerHTML = '';
    }

    function setRows(temps, values) {
        clearRows();
        for (let i = 0; i < temps.length; i++) addRow(temps[i], values[i]);
        if (!tbody.children.length) addRow();
    }

    // Initialize from any existing hidden-field JSON (e.g. failed validation re-render)
    function initFromHiddenField() {
        try {
            const data = JSON.parse(hiddenField.value);
            if (data && Array.isArray(data.temperature) && Array.isArray(data.value)) {
                setRows(data.temperature, data.value);
                return;
            }
        } catch (e) { /* empty or invalid — start blank */ }
        setRows([], []);
        addRow(); // two starter rows
    }

    // Paste handler: accept two columns from Excel (tabs) or CSV (semicolons)
    table.addEventListener('paste', function (e) {
        const text = (e.clipboardData || window.clipboardData).getData('text');
        if (!text || !/[\t;\r\n]/.test(text)) return; // single value — default paste
        e.preventDefault();
        const pairs = [];
        text.split(/\r?\n/).forEach(function (line) {
            if (!line.trim()) return;
            const cells = line.split(/\t|;/);
            if (cells.length < 2) return;
            const t = parseCell(cells[0]);
            const v = parseCell(cells[1]);
            if (t !== null && v !== null) pairs.push([t, v]);
        });
        if (!pairs.length) {
            errorsDiv.textContent = 'Could not read pasted data. Paste two columns: temperature and value.';
            return;
        }
        errorsDiv.textContent = '';
        const existing = collectRows();
        const temps = existing.temps.concat(pairs.map(function (p) { return p[0]; }));
        const values = existing.values.concat(pairs.map(function (p) { return p[1]; }));
        setRows(temps, values);
    });

    addRowBtn.addEventListener('click', function () { addRow(); });

    // Serialize to the hidden field on submit; block obviously invalid curves
    form.addEventListener('submit', function (e) {
        const isCurveType = propertyType && (propertyType.value === 'curve' || propertyType.value === 'table');
        if (!isCurveType) {
            hiddenField.value = '';
            return;
        }
        const rows = collectRows();
        if (rows.badRows > 0) {
            e.preventDefault();
            errorsDiv.textContent = 'Some rows contain non-numeric input. Fix or remove them.';
            return;
        }
        if (rows.temps.length < 2) {
            e.preventDefault();
            errorsDiv.textContent = 'Enter at least 2 temperature/value points.';
            return;
        }
        errorsDiv.textContent = '';
        hiddenField.value = JSON.stringify({ temperature: rows.temps, value: rows.values });
    });

    // Edit buttons on the existing-properties table prefill the form
    document.querySelectorAll('.js-edit-prop').forEach(function (btn) {
        btn.addEventListener('click', function () {
            const name = btn.dataset.propName;
            const type = btn.dataset.propType;
            let data = {};
            try { data = JSON.parse(btn.dataset.propData); } catch (e) { /* leave empty */ }

            const nameSelect = document.getElementById('property_name');
            const customGroup = document.getElementById('custom_name_group');
            const customInput = document.querySelector('#custom_name_group input');
            const hasOption = Array.prototype.some.call(nameSelect.options, function (o) {
                return o.value === name;
            });
            nameSelect.value = hasOption ? name : 'custom';
            customGroup.style.display = hasOption ? 'none' : 'block';
            if (!hasOption && customInput) customInput.value = name;

            const typeSelect = document.getElementById('property_type');
            typeSelect.value = type;
            typeSelect.dispatchEvent(new Event('change'));

            const unitsInput = document.querySelector('input[name="units"]');
            if (unitsInput) unitsInput.value = btn.dataset.propUnits || '';
            const depsInput = document.querySelector('input[name="dependencies"]');
            if (depsInput) depsInput.value = btn.dataset.propDeps || '';
            const notesInput = document.querySelector('[name="notes"]');
            if (notesInput) notesInput.value = btn.dataset.propNotes || '';

            if (type === 'constant') {
                const constInput = document.querySelector('input[name="constant_value"]');
                if (constInput && data.value !== undefined && data.value !== null) {
                    constInput.value = data.value;
                }
            } else if (type === 'curve' || type === 'table') {
                if (Array.isArray(data.temperature) && Array.isArray(data.value)) {
                    setRows(data.temperature, data.value);
                }
            } else if (type === 'polynomial') {
                const varInput = document.querySelector('input[name="polynomial_variable"]');
                const coeffInput = document.querySelector('input[name="polynomial_coefficients"]');
                if (varInput) varInput.value = data.variable || 'temperature';
                if (coeffInput && Array.isArray(data.coefficients)) {
                    coeffInput.value = data.coefficients.join(', ');
                }
            } else if (type === 'equation') {
                const eqInput = document.querySelector('input[name="equation"]');
                const eqVarsInput = document.querySelector('input[name="equation_variables"]');
                if (eqInput) eqInput.value = data.equation || '';
                if (eqVarsInput) eqVarsInput.value = JSON.stringify(data.variables || {});
            }

            document.querySelector('#property_name').scrollIntoView({ behavior: 'smooth', block: 'start' });
        });
    });

    initFromHiddenField();
});
