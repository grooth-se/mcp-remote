from datetime import datetime, timezone
from app.extensions import db


class MetricSample(db.Model):
    """Raw metrics sample, one row per scope per collection interval."""
    __tablename__ = 'metric_sample'

    id = db.Column(db.Integer, primary_key=True)
    ts = db.Column(db.DateTime, index=True, default=lambda: datetime.now(timezone.utc))
    scope = db.Column(db.String(64), index=True)  # 'host' or container name
    cpu_pct = db.Column(db.Float)
    mem_used = db.Column(db.BigInteger)   # bytes
    mem_total = db.Column(db.BigInteger)  # bytes (containers: memory limit)
    disk_json = db.Column(db.Text)        # per-mount usage as JSON (host only)
    extra_json = db.Column(db.Text)       # loadavg/net/io as JSON


class MetricHourly(db.Model):
    """Hourly min/avg/max roll-up of MetricSample, kept longer than raw."""
    __tablename__ = 'metric_hourly'

    id = db.Column(db.Integer, primary_key=True)
    hour = db.Column(db.DateTime, index=True)
    scope = db.Column(db.String(64), index=True)
    metric = db.Column(db.String(64), index=True)  # 'cpu_pct', 'mem_pct', 'disk_pct:<mount>'
    v_min = db.Column(db.Float)
    v_avg = db.Column(db.Float)
    v_max = db.Column(db.Float)
