import json
from datetime import datetime, timedelta, timezone

from flask import current_app

from app.extensions import db
from app.models.log import AccessLog
from app.models.metrics import MetricSample, MetricHourly
from app.services.system_metrics import get_host_metrics, get_container_metrics


def _utcnow_naive():
    # SQLite hands naive datetimes back, so all Python-side arithmetic in
    # this module uses naive UTC to keep comparisons consistent.
    return datetime.now(timezone.utc).replace(tzinfo=None)


def collect_once(cpu_interval=None):
    """Store one MetricSample for the host and each running container."""
    host = get_host_metrics(cpu_interval=cpu_interval)
    rows = [MetricSample(
        scope='host',
        cpu_pct=host['cpu_percent'],
        mem_used=host['memory']['used'],
        mem_total=host['memory']['total'],
        disk_json=json.dumps(host['disks']),
        extra_json=json.dumps({
            'load_avg': host['load_avg'],
            'swap': host['swap'],
            'net_io': host['net_io'],
            'disk_io': host['disk_io'],
            'process_count': host['process_count'],
            'uptime_seconds': host['uptime_seconds'],
        }),
    )]
    containers = get_container_metrics()
    if isinstance(containers, list):
        for c in containers:
            if c['state'] != 'running':
                continue
            rows.append(MetricSample(
                scope=c['name'],
                cpu_pct=c['cpu_percent'],
                mem_used=c['mem_used'],
                mem_total=c['mem_limit'],
                extra_json=json.dumps({
                    'net_rx': c['net_rx'],
                    'net_tx': c['net_tx'],
                    'restart_count': c['restart_count'],
                }),
            ))
    db.session.add_all(rows)
    db.session.commit()
    return len(rows)


def rollup_metrics():
    """Aggregate raw samples into hourly min/avg/max rows.

    Rolls up completed hours after the newest already-rolled-up hour, so
    repeated runs are idempotent and cheap.
    """
    current_hour = _utcnow_naive().replace(minute=0, second=0, microsecond=0)
    query = MetricSample.query.filter(MetricSample.ts < current_hour)
    last_hour = db.session.query(db.func.max(MetricHourly.hour)).scalar()
    if last_hour is not None:
        query = query.filter(MetricSample.ts >= last_hour + timedelta(hours=1))

    buckets = {}
    for s in query.all():
        hour = s.ts.replace(minute=0, second=0, microsecond=0)
        metrics = {}
        if s.cpu_pct is not None:
            metrics['cpu_pct'] = s.cpu_pct
        if s.mem_used is not None and s.mem_total:
            metrics['mem_pct'] = s.mem_used * 100.0 / s.mem_total
        if s.disk_json:
            for d in json.loads(s.disk_json):
                metrics[f"disk_pct:{d['mount']}"] = d['percent']
        for name, value in metrics.items():
            buckets.setdefault((hour, s.scope, name), []).append(value)

    for (hour, scope, metric), values in buckets.items():
        MetricHourly.query.filter_by(hour=hour, scope=scope, metric=metric).delete()
        db.session.add(MetricHourly(
            hour=hour, scope=scope, metric=metric,
            v_min=min(values), v_avg=sum(values) / len(values), v_max=max(values)))
    db.session.commit()
    return len(buckets)


def purge_metrics():
    """Delete raw samples and hourly roll-ups past their retention windows."""
    now = _utcnow_naive()
    raw_cutoff = now - timedelta(days=current_app.config['METRICS_RAW_DAYS'])
    hourly_cutoff = now - timedelta(days=current_app.config['METRICS_HOURLY_DAYS'])
    raw = MetricSample.query.filter(MetricSample.ts < raw_cutoff).delete()
    hourly = MetricHourly.query.filter(MetricHourly.hour < hourly_cutoff).delete()
    db.session.commit()
    return raw, hourly


def purge_access_logs(days=None):
    """Delete access-log entries older than the retention window (GDPR)."""
    if days is None:
        days = current_app.config['ACCESS_LOG_RETENTION_DAYS']
    cutoff = _utcnow_naive() - timedelta(days=days)
    count = AccessLog.query.filter(AccessLog.timestamp < cutoff).delete()
    db.session.commit()
    return count
