import time

import click
from flask import current_app

from app.extensions import db
from app.services import metrics_collector


def register_cli(app):
    @app.cli.command('collect-metrics')
    def collect_metrics():
        """Store one metrics sample (host + containers)."""
        count = metrics_collector.collect_once(cpu_interval=0.5)
        click.echo(f'Stored {count} sample(s).')

    @app.cli.command('rollup-metrics')
    def rollup_metrics():
        """Roll raw samples up to hourly min/avg/max and purge old metrics."""
        buckets = metrics_collector.rollup_metrics()
        raw, hourly = metrics_collector.purge_metrics()
        click.echo(f'Rolled up {buckets} bucket(s); purged {raw} raw / {hourly} hourly row(s).')

    @app.cli.command('purge-logs')
    @click.option('--days', type=int, default=None,
                  help='Retention in days (default: ACCESS_LOG_RETENTION_DAYS).')
    def purge_logs(days):
        """Delete access-log entries older than the retention window."""
        count = metrics_collector.purge_access_logs(days)
        click.echo(f'Purged {count} access-log row(s).')

    @app.cli.command('collect-loop')
    def collect_loop():
        """Sampling loop for the dedicated collector container.

        Samples every COLLECT_INTERVAL_SECONDS and runs roll-up + retention
        purges once an hour. Must run as a single process so CPU %% can be
        measured as a delta between successive samples.
        """
        interval = current_app.config['COLLECT_INTERVAL_SECONDS']
        click.echo(f'Collector loop started, interval {interval}s.')
        # Prime psutil/docker CPU counters; the first delta-based reading
        # is meaningless, so this sample is not stored.
        try:
            from app.services.system_metrics import get_host_metrics, get_container_metrics
            get_host_metrics()
            get_container_metrics()
        except Exception:
            pass
        last_maintenance = 0.0
        while True:
            started = time.monotonic()
            try:
                metrics_collector.collect_once()
            except Exception as e:
                db.session.rollback()
                click.echo(f'collect failed: {e}', err=True)
            if time.monotonic() - last_maintenance >= 3600:
                try:
                    metrics_collector.rollup_metrics()
                    metrics_collector.purge_metrics()
                    metrics_collector.purge_access_logs()
                    last_maintenance = time.monotonic()
                except Exception as e:
                    db.session.rollback()
                    click.echo(f'maintenance failed: {e}', err=True)
            time.sleep(max(1.0, interval - (time.monotonic() - started)))
