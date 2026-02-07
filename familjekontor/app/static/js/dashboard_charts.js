// Dashboard Charts - Chart.js integration

function initRevenueExpenseChart(canvasId) {
    fetch('/api/revenue-expense-chart')
        .then(r => r.json())
        .then(data => {
            const ctx = document.getElementById(canvasId);
            if (!ctx) return;
            new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: data.labels,
                    datasets: [
                        {
                            label: 'Intakter',
                            data: data.revenue,
                            backgroundColor: 'rgba(25, 135, 84, 0.7)',
                            borderColor: 'rgba(25, 135, 84, 1)',
                            borderWidth: 1,
                        },
                        {
                            label: 'Kostnader',
                            data: data.expenses,
                            backgroundColor: 'rgba(220, 53, 69, 0.7)',
                            borderColor: 'rgba(220, 53, 69, 1)',
                            borderWidth: 1,
                        }
                    ]
                },
                options: {
                    responsive: true,
                    plugins: {
                        legend: { position: 'top' },
                        title: { display: true, text: 'Intakter & Kostnader per Manad' }
                    },
                    scales: {
                        y: {
                            beginAtZero: true,
                            ticks: {
                                callback: function(value) {
                                    return value.toLocaleString('sv-SE') + ' kr';
                                }
                            }
                        }
                    }
                }
            });
        });
}

function initCashFlowChart(canvasId) {
    fetch('/api/cash-flow-chart')
        .then(r => r.json())
        .then(data => {
            const ctx = document.getElementById(canvasId);
            if (!ctx) return;
            new Chart(ctx, {
                type: 'line',
                data: {
                    labels: data.labels,
                    datasets: [
                        {
                            label: 'Kassaflode',
                            data: data.cash_flow,
                            borderColor: 'rgba(13, 110, 253, 1)',
                            backgroundColor: 'rgba(13, 110, 253, 0.1)',
                            fill: true,
                            tension: 0.3,
                        },
                        {
                            label: 'Ack. saldo',
                            data: data.balance,
                            borderColor: 'rgba(108, 117, 125, 1)',
                            borderDash: [5, 5],
                            fill: false,
                            tension: 0.3,
                        }
                    ]
                },
                options: {
                    responsive: true,
                    plugins: {
                        legend: { position: 'top' },
                        title: { display: true, text: 'Kassaflode' }
                    },
                    scales: {
                        y: {
                            ticks: {
                                callback: function(value) {
                                    return value.toLocaleString('sv-SE') + ' kr';
                                }
                            }
                        }
                    }
                }
            });
        });
}

document.addEventListener('DOMContentLoaded', function() {
    if (document.getElementById('revenueExpenseChart')) {
        initRevenueExpenseChart('revenueExpenseChart');
    }
    if (document.getElementById('cashFlowChart')) {
        initCashFlowChart('cashFlowChart');
    }
});
