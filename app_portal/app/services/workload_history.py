import json
from datetime import datetime, timedelta, timezone

from app.extensions import db
from app.models.metrics import MetricSample, MetricHourly

# range key -> (window, source table)
RANGES = {
    '1h': (timedelta(hours=1), 'raw'),
    '24h': (timedelta(hours=24), 'raw'),
    '7d': (timedelta(days=7), 'hourly'),
    '30d': (timedelta(days=30), 'hourly'),
}
METRICS = ('cpu_pct', 'mem_pct', 'disk_pct')
TOP_N = 5


def _utcnow_naive():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _iso(ts):
    # Timestamps are naive UTC; the 'Z' lets the browser render local time.
    return ts.isoformat() + 'Z'


def get_workload_series(range_key, scope, metric):
    """Return (source, series) for a chart, where series is a list of
    {'label', 'points'} dicts. Raises ValueError on bad parameters."""
    if range_key not in RANGES:
        raise ValueError(f'invalid range: {range_key}')
    if metric not in METRICS:
        raise ValueError(f'invalid metric: {metric}')
    if metric == 'disk_pct' and scope != 'host':
        raise ValueError('disk_pct is only available for scope=host')

    window, source = RANGES[range_key]
    since = _utcnow_naive() - window
    if scope == 'containers':
        series = _top_container_series(metric, since, source)
    elif source == 'raw':
        series = _raw_series(scope, metric, since)
    else:
        series = _hourly_series(scope, metric, since)
    return source, series


def _sample_value(sample, metric):
    if metric == 'cpu_pct':
        return sample.cpu_pct
    if metric == 'mem_pct' and sample.mem_used is not None and sample.mem_total:
        return sample.mem_used * 100.0 / sample.mem_total
    return None


def _raw_series(scope, metric, since):
    samples = (MetricSample.query
               .filter(MetricSample.scope == scope, MetricSample.ts >= since)
               .order_by(MetricSample.ts).all())
    if metric == 'disk_pct':
        by_mount = {}
        for s in samples:
            for d in json.loads(s.disk_json or '[]'):
                by_mount.setdefault(d['mount'], []).append(
                    {'t': _iso(s.ts), 'v': d['percent']})
        return [{'label': mount, 'points': points}
                for mount, points in sorted(by_mount.items())]
    points = []
    for s in samples:
        value = _sample_value(s, metric)
        if value is not None:
            points.append({'t': _iso(s.ts), 'v': round(value, 2)})
    return [{'label': scope, 'points': points}]


def _hourly_point(row):
    return {'t': _iso(row.hour), 'min': round(row.v_min, 2),
            'avg': round(row.v_avg, 2), 'max': round(row.v_max, 2)}


def _hourly_series(scope, metric, since):
    if metric == 'disk_pct':
        rows = (MetricHourly.query
                .filter(MetricHourly.scope == scope,
                        MetricHourly.metric.like('disk_pct:%'),
                        MetricHourly.hour >= since)
                .order_by(MetricHourly.hour).all())
        by_mount = {}
        for r in rows:
            mount = r.metric.split(':', 1)[1]
            by_mount.setdefault(mount, []).append(_hourly_point(r))
        return [{'label': mount, 'points': points}
                for mount, points in sorted(by_mount.items())]
    rows = (MetricHourly.query
            .filter(MetricHourly.scope == scope, MetricHourly.metric == metric,
                    MetricHourly.hour >= since)
            .order_by(MetricHourly.hour).all())
    return [{'label': scope, 'points': [_hourly_point(r) for r in rows]}]


def _top_container_series(metric, since, source):
    """Series for the TOP_N busiest containers over the range. Names are
    sorted alphabetically so a container keeps its color across ranges."""
    if source == 'raw':
        if metric == 'cpu_pct':
            rank = db.func.avg(MetricSample.cpu_pct)
        else:
            rank = db.func.avg(MetricSample.mem_used * 100.0 / MetricSample.mem_total)
        top = (db.session.query(MetricSample.scope)
               .filter(MetricSample.scope != 'host', MetricSample.ts >= since)
               .group_by(MetricSample.scope)
               .order_by(rank.desc()).limit(TOP_N).all())
        names = sorted(name for (name,) in top)
        return [_raw_series(name, metric, since)[0] for name in names]

    top = (db.session.query(MetricHourly.scope)
           .filter(MetricHourly.scope != 'host', MetricHourly.metric == metric,
                   MetricHourly.hour >= since)
           .group_by(MetricHourly.scope)
           .order_by(db.func.avg(MetricHourly.v_avg).desc()).limit(TOP_N).all())
    names = sorted(name for (name,) in top)
    return [_hourly_series(name, metric, since)[0] for name in names]
