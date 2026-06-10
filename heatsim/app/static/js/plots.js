/*
 * Interactive simulation result plots.
 *
 * Every <div class="js-plot" data-plot-url="..."> is filled with a Plotly
 * line chart fetched from the simulation plot-data JSON endpoint. Zoom
 * (drag/scroll), pan and reset come from the standard Plotly modebar;
 * double-click resets the view.
 */
(function () {
    'use strict';

    var PLOT_CONFIG = {
        responsive: true,
        displaylogo: false,
        scrollZoom: true,
        modeBarButtonsToRemove: ['select2d', 'lasso2d', 'autoScale2d']
    };

    function buildLayout(layout) {
        layout = layout || {};
        var out = {
            title: { text: layout.title || '', font: { size: 14 } },
            xaxis: { title: { text: layout.xaxis_title || '' }, gridcolor: 'rgba(0,0,0,0.1)' },
            yaxis: { title: { text: layout.yaxis_title || '' }, gridcolor: 'rgba(0,0,0,0.1)' },
            margin: { t: 50, r: 20, b: 50, l: 60 },
            hovermode: 'x unified',
            plot_bgcolor: 'white',
            paper_bgcolor: 'white',
            legend: { orientation: 'h', y: -0.2 }
        };
        if (layout.shapes) out.shapes = layout.shapes;
        if (layout.annotations) out.annotations = layout.annotations;
        return out;
    }

    function showError(el, message) {
        el.innerHTML = '';
        var p = document.createElement('p');
        p.className = 'text-muted my-4';
        p.textContent = message || 'Plot unavailable';
        el.appendChild(p);
    }

    function renderPlot(el, url, useReact) {
        el.innerHTML = '<div class="spinner-border text-secondary my-4" role="status">' +
            '<span class="visually-hidden">Loading…</span></div>';
        fetch(url)
            .then(function (resp) {
                return resp.json().then(function (data) {
                    if (!resp.ok) throw new Error(data.error || 'Plot unavailable');
                    return data;
                });
            })
            .then(function (data) {
                el.innerHTML = '';
                var fn = useReact ? Plotly.react : Plotly.newPlot;
                fn(el, data.traces, buildLayout(data.layout), PLOT_CONFIG);
            })
            .catch(function (err) {
                showError(el, err.message);
            });
    }

    function initPlots() {
        if (typeof Plotly === 'undefined') return;
        document.querySelectorAll('.js-plot[data-plot-url]').forEach(function (el) {
            renderPlot(el, el.dataset.plotUrl, false);
        });
    }

    window.heatsimPlots = { initPlots: initPlots, renderPlot: renderPlot };

    document.addEventListener('DOMContentLoaded', initPlots);
})();
