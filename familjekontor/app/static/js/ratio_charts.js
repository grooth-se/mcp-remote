/**
 * Ratio charts — horizontal bar for current year, line for multi-year trend.
 */

function initRatioBarChart(canvasId, data) {
    var ctx = document.getElementById(canvasId);
    if (!ctx) return;

    var colors = data.statuses.map(function(s) {
        if (s === 'good') return 'rgba(25, 135, 84, 0.7)';
        if (s === 'warning') return 'rgba(255, 193, 7, 0.7)';
        if (s === 'danger') return 'rgba(220, 53, 69, 0.7)';
        return 'rgba(108, 117, 125, 0.5)';
    });

    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: data.labels,
            datasets: [{
                label: 'Värde',
                data: data.values,
                backgroundColor: colors,
                borderColor: colors.map(function(c) { return c.replace('0.7', '1'); }),
                borderWidth: 1,
            }]
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: function(ctx) {
                            return ctx.parsed.x !== null ? ctx.parsed.x.toLocaleString('sv-SE') : '-';
                        }
                    }
                }
            },
            scales: {
                x: { beginAtZero: true }
            }
        }
    });
}

function initRatioTrendChart(canvasId, apiUrl) {
    var ctx = document.getElementById(canvasId);
    if (!ctx) return;

    fetch(apiUrl)
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (!data.years || data.years.length === 0) return;

            var colors = [
                'rgb(13, 110, 253)',
                'rgb(25, 135, 84)',
                'rgb(255, 193, 7)',
                'rgb(220, 53, 69)',
                'rgb(111, 66, 193)',
                'rgb(253, 126, 20)',
                'rgb(32, 201, 151)',
                'rgb(214, 51, 132)',
                'rgb(13, 202, 240)',
            ];

            var datasets = [];
            var keys = Object.keys(data.ratios);
            var labels = {
                'gross_margin': 'Bruttomarginal %',
                'operating_margin': 'Rörelsemarginal %',
                'net_margin': 'Nettomarginal %',
                'roe': 'ROE %',
                'current_ratio': 'Balanslikviditet',
                'quick_ratio': 'Kassalikviditet',
                'equity_ratio': 'Soliditet %',
                'debt_to_equity': 'Skuldsättningsgrad',
                'asset_turnover': 'Kap. oms.hastighet',
            };

            keys.forEach(function(key, i) {
                datasets.push({
                    label: labels[key] || key,
                    data: data.ratios[key],
                    borderColor: colors[i % colors.length],
                    backgroundColor: 'transparent',
                    tension: 0.3,
                    pointRadius: 4,
                });
            });

            new Chart(ctx, {
                type: 'line',
                data: {
                    labels: data.years,
                    datasets: datasets,
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 10 } } },
                    },
                    scales: {
                        x: { title: { display: true, text: 'År' } },
                        y: { title: { display: true, text: 'Värde' } },
                    }
                }
            });
        });
}
