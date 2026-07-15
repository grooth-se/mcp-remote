// Live polling for the admin monitoring pages. GET-only, no CSRF needed.
document.addEventListener('DOMContentLoaded', function () {
    const root = document.getElementById('monitor-status');
    if (!root) return;

    const dataUrl = root.dataset.url;
    const intervalMs = (parseInt(root.dataset.interval, 10) || 5) * 1000;
    let timer = null;

    function fmtBytes(bytes) {
        if (bytes === null || bytes === undefined) return '–';
        const units = ['B', 'KB', 'MB', 'GB', 'TB'];
        let i = 0;
        let v = bytes;
        while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
        return v.toFixed(v >= 100 || i === 0 ? 0 : 1) + ' ' + units[i];
    }

    function fmtUptime(seconds) {
        if (!seconds) return '–';
        const d = Math.floor(seconds / 86400);
        const h = Math.floor((seconds % 86400) / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        return d > 0 ? d + 'd ' + h + 'h' : h + 'h ' + m + 'm';
    }

    function setText(id, text) {
        const el = document.getElementById(id);
        if (el) el.textContent = text;
    }

    function setBar(id, pct) {
        const el = document.getElementById(id);
        if (!el) return;
        const v = pct || 0;
        el.style.width = v + '%';
        el.className = 'progress-bar' + (v > 90 ? ' bg-danger' : v > 75 ? ' bg-warning' : '');
    }

    function barCell(pct) {
        const v = pct === null || pct === undefined ? 0 : pct;
        const cls = v > 90 ? ' bg-danger' : v > 75 ? ' bg-warning' : '';
        return '<div class="d-flex align-items-center">' +
            '<div class="progress flex-grow-1 me-2" style="height: 6px;">' +
            '<div class="progress-bar' + cls + '" style="width: ' + v + '%"></div></div>' +
            '<small>' + v.toFixed(1) + '%</small></div>';
    }

    function esc(s) {
        const div = document.createElement('div');
        div.textContent = s === null || s === undefined ? '–' : String(s);
        return div.innerHTML;
    }

    function renderHost(host) {
        setText('host-cpu', host.cpu_percent.toFixed(1) + '%');
        setBar('host-cpu-bar', host.cpu_percent);
        setText('host-cpu-cores', host.cpu_count + ' cores');
        setText('host-mem', host.memory.percent.toFixed(1) + '%');
        setBar('host-mem-bar', host.memory.percent);
        setText('host-mem-detail', fmtBytes(host.memory.used) + ' / ' + fmtBytes(host.memory.total));
        const la = host.load_avg;
        setText('host-load', la['1m'] === null ? '–'
            : la['1m'].toFixed(2) + ' / ' + la['5m'].toFixed(2) + ' / ' + la['15m'].toFixed(2));
        setText('host-uptime', fmtUptime(host.uptime_seconds));
        setText('host-procs', host.process_count + ' processes');

        const rows = host.disks.map(function (d) {
            return '<tr><td><code>' + esc(d.mount) + '</code></td>' +
                '<td>' + fmtBytes(d.used) + '</td>' +
                '<td>' + fmtBytes(d.free) + '</td>' +
                '<td>' + fmtBytes(d.total) + '</td>' +
                '<td>' + barCell(d.percent) + '</td></tr>';
        });
        document.getElementById('disk-table').innerHTML = rows.join('') ||
            '<tr><td colspan="5" class="text-center text-muted py-3">No disks reported.</td></tr>';
    }

    function renderContainers(containers) {
        const card = document.getElementById('container-card');
        if (containers === null) { card.classList.add('d-none'); return; }
        card.classList.remove('d-none');
        const tbody = document.getElementById('container-table');
        if (containers.error) {
            tbody.innerHTML = '<tr><td colspan="7" class="text-danger py-3">' +
                esc(containers.error) + '</td></tr>';
            return;
        }
        tbody.innerHTML = containers.map(function (c) {
            const stateBadge = c.state === 'running'
                ? '<span class="badge bg-success">running</span>'
                : '<span class="badge bg-secondary">' + esc(c.state) + '</span>';
            const health = c.health ? ' <span class="badge bg-' +
                (c.health === 'healthy' ? 'success' : 'warning') + '">' + esc(c.health) + '</span>' : '';
            return '<tr><td><strong>' + esc(c.name) + '</strong></td>' +
                '<td>' + stateBadge + health + '</td>' +
                '<td><small class="text-muted">' + esc(c.status) + '</small></td>' +
                '<td>' + (c.cpu_percent === null ? '–' : c.cpu_percent.toFixed(1) + '%') + '</td>' +
                '<td>' + (c.mem_used === null ? '–'
                    : fmtBytes(c.mem_used) + ' / ' + fmtBytes(c.mem_limit)) + '</td>' +
                '<td><small>' + fmtBytes(c.net_rx) + ' / ' + fmtBytes(c.net_tx) + '</small></td>' +
                '<td>' + esc(c.restart_count) + '</td></tr>';
        }).join('') || '<tr><td colspan="7" class="text-center text-muted py-3">No containers.</td></tr>';
    }

    function poll() {
        const spinner = document.getElementById('monitor-spinner');
        spinner.classList.remove('d-none');
        fetch(dataUrl, { headers: { 'Accept': 'application/json' } })
            .then(function (resp) {
                if (!resp.ok) throw new Error('HTTP ' + resp.status);
                return resp.json();
            })
            .then(function (data) {
                document.getElementById('monitor-error').classList.add('d-none');
                renderHost(data.host);
                renderContainers(data.containers);
                setText('monitor-updated', 'Updated ' + new Date().toLocaleTimeString());
            })
            .catch(function (err) {
                const el = document.getElementById('monitor-error');
                el.textContent = 'Failed to load status: ' + err.message;
                el.classList.remove('d-none');
            })
            .finally(function () {
                spinner.classList.add('d-none');
                timer = setTimeout(poll, intervalMs);
            });
    }

    document.addEventListener('visibilitychange', function () {
        if (document.hidden) {
            if (timer) { clearTimeout(timer); timer = null; }
        } else if (!timer) {
            poll();
        }
    });

    poll();
});

// Workload history charts (Chart.js, loaded from CDN on that page only).
document.addEventListener('DOMContentLoaded', function () {
    const root = document.getElementById('workload-charts');
    if (!root || typeof Chart === 'undefined') return;

    const dataUrl = root.dataset.url;
    // Fixed categorical order (colorblind-safe); a series keeps its slot.
    const palette = ['#2a78d6', '#1baf7a', '#eda100', '#008300',
                     '#4a3aa7', '#e34948', '#e87ba4', '#eb6834'];
    const charts = new Map();  // canvas -> Chart instance

    function fmtTime(iso, source) {
        const d = new Date(iso);
        if (source === 'hourly') {
            return d.toLocaleDateString([], { day: '2-digit', month: '2-digit' }) +
                ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        }
        return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }

    function buildDatasets(payload, times) {
        const datasets = [];
        const banded = payload.source === 'hourly' && payload.series.length === 1;
        payload.series.forEach(function (s, i) {
            const color = palette[i % palette.length];
            const byTime = new Map(s.points.map(function (p) { return [p.t, p]; }));
            const value = function (t) {
                const p = byTime.get(t);
                if (!p) return null;
                return payload.source === 'hourly' ? p.avg : p.v;
            };
            if (banded) {
                datasets.push({
                    label: '_min', data: times.map(function (t) {
                        const p = byTime.get(t); return p ? p.min : null;
                    }),
                    borderColor: 'transparent', pointRadius: 0, fill: false, spanGaps: true,
                });
                datasets.push({
                    label: '_range', data: times.map(function (t) {
                        const p = byTime.get(t); return p ? p.max : null;
                    }),
                    borderColor: 'transparent', backgroundColor: color + '33',
                    pointRadius: 0, fill: '-1', spanGaps: true,
                });
            }
            datasets.push({
                label: s.label, data: times.map(value),
                borderColor: color, backgroundColor: color,
                borderWidth: 2, pointRadius: 0, tension: 0.2,
                spanGaps: true, fill: false,
            });
        });
        return datasets;
    }

    function render(canvas, payload) {
        const wrapper = canvas.closest('.card-body');
        const noData = wrapper.querySelector('.no-data');
        const hasPoints = payload.series.some(function (s) { return s.points.length; });
        canvas.parentElement.classList.toggle('d-none', !hasPoints);
        noData.classList.toggle('d-none', hasPoints);
        if (charts.has(canvas)) { charts.get(canvas).destroy(); charts.delete(canvas); }
        if (!hasPoints) return;

        const times = Array.from(new Set(payload.series.flatMap(function (s) {
            return s.points.map(function (p) { return p.t; });
        }))).sort();

        charts.set(canvas, new Chart(canvas, {
            type: 'line',
            data: {
                labels: times.map(function (t) { return fmtTime(t, payload.source); }),
                datasets: buildDatasets(payload, times),
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                interaction: { mode: 'index', intersect: false },
                scales: {
                    y: { beginAtZero: true, suggestedMax: 100 },
                    x: { ticks: { maxTicksLimit: 10, maxRotation: 0 } },
                },
                plugins: {
                    legend: {
                        display: payload.series.length > 1,
                        labels: {
                            filter: function (item) { return !item.text.startsWith('_'); },
                        },
                    },
                    tooltip: {
                        filter: function (item) { return !item.dataset.label.startsWith('_'); },
                    },
                },
            },
        }));
    }

    function loadAll() {
        const range = root.dataset.range;
        root.querySelectorAll('canvas[data-metric]').forEach(function (canvas) {
            const params = new URLSearchParams({
                range: range, scope: canvas.dataset.scope, metric: canvas.dataset.metric,
            });
            fetch(dataUrl + '?' + params, { headers: { 'Accept': 'application/json' } })
                .then(function (resp) {
                    if (!resp.ok) throw new Error('HTTP ' + resp.status);
                    return resp.json();
                })
                .then(function (payload) { render(canvas, payload); })
                .catch(function () {
                    const noData = canvas.closest('.card-body').querySelector('.no-data');
                    noData.textContent = 'Failed to load data.';
                    noData.classList.remove('d-none');
                });
        });
    }

    document.querySelectorAll('#workload-range button').forEach(function (btn) {
        btn.addEventListener('click', function () {
            document.querySelectorAll('#workload-range button').forEach(function (b) {
                b.classList.toggle('active', b === btn);
            });
            root.dataset.range = btn.dataset.range;
            loadAll();
        });
    });

    loadAll();
});

// Usage-per-app bar chart on the App Usage page.
document.addEventListener('DOMContentLoaded', function () {
    const wrap = document.getElementById('usage-chart-wrap');
    if (!wrap || typeof Chart === 'undefined') return;

    fetch(wrap.dataset.url, { headers: { 'Accept': 'application/json' } })
        .then(function (resp) {
            if (!resp.ok) throw new Error('HTTP ' + resp.status);
            return resp.json();
        })
        .then(function (data) {
            const summary = data.summary;
            if (!summary.length) return;
            new Chart(document.getElementById('usage-chart'), {
                type: 'bar',
                data: {
                    labels: summary.map(function (r) { return r.app_name; }),
                    datasets: [
                        { label: 'Launches', data: summary.map(function (r) { return r.access_app; }),
                          backgroundColor: '#2a78d6', borderRadius: 4 },
                        { label: 'Validations', data: summary.map(function (r) { return r.validate; }),
                          backgroundColor: '#1baf7a', borderRadius: 4 },
                        { label: 'Denied', data: summary.map(function (r) { return r.denied; }),
                          backgroundColor: '#e34948', borderRadius: 4 },
                    ],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: false,
                    interaction: { mode: 'index', intersect: false },
                    scales: { y: { beginAtZero: true, ticks: { precision: 0 } } },
                },
            });
        })
        .catch(function () { /* chart is optional; tables carry the data */ });
});
