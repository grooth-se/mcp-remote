"""Tests for the admin monitoring area (/admin/system/status|workload|usage)."""
import io
import json
from datetime import timedelta

import pytest

from app.extensions import db as _db
from app.models.log import AccessLog
from app.models.metrics import MetricSample, MetricHourly
from app.services import metrics_collector, system_metrics

MONITORING_ROUTES = [
    '/admin/system/status',
    '/admin/system/workload',
    '/admin/system/usage',
]


@pytest.mark.parametrize('route', MONITORING_ROUTES)
def test_monitoring_forbidden_for_normal_user(user_logged_in_client, route):
    resp = user_logged_in_client.get(route)
    assert resp.status_code == 403


@pytest.mark.parametrize('route', MONITORING_ROUTES)
def test_monitoring_redirects_anonymous_to_login(client, route):
    resp = client.get(route)
    assert resp.status_code == 302
    assert '/login' in resp.headers['Location']


@pytest.mark.parametrize('route', MONITORING_ROUTES)
def test_monitoring_ok_for_admin(logged_in_client, route):
    resp = logged_in_client.get(route)
    assert resp.status_code == 200


def test_monitoring_nav_entries_visible_for_admin(logged_in_client):
    resp = logged_in_client.get('/admin/system/status')
    html = resp.get_data(as_text=True)
    assert 'Server Status' in html
    assert 'Workload History' in html
    assert 'App Usage' in html


# --- Phase 1: live server status ---

def test_status_data_forbidden_for_normal_user(user_logged_in_client):
    resp = user_logged_in_client.get('/admin/system/status/data')
    assert resp.status_code == 403


def test_status_data_returns_host_metrics(logged_in_client):
    resp = logged_in_client.get('/admin/system/status/data')
    assert resp.status_code == 200
    data = resp.get_json()
    host = data['host']
    for key in ('cpu_percent', 'memory', 'disks', 'load_avg', 'uptime_seconds',
                'process_count', 'cpu_count'):
        assert key in host
    assert host['memory']['total'] > 0
    assert isinstance(host['disks'], list)
    # No DOCKER_PROXY_URL in TestingConfig -> containers hidden
    assert data['containers'] is None


def test_container_metrics_none_without_proxy(app):
    with app.app_context():
        assert system_metrics.get_container_metrics() is None


def test_container_metrics_error_when_proxy_unreachable(app):
    app.config['DOCKER_PROXY_URL'] = 'http://127.0.0.1:1'  # nothing listens here
    with app.app_context():
        result = system_metrics.get_container_metrics()
    assert 'error' in result


def _fake_urlopen_factory(responses):
    """Return a urlopen stub serving canned JSON keyed by URL substring."""
    class FakeResponse(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_urlopen(req, timeout=None):
        url = req.full_url
        for fragment, payload in responses.items():
            if fragment in url:
                return FakeResponse(json.dumps(payload).encode())
        raise AssertionError(f'unexpected URL {url}')

    return fake_urlopen


def test_container_metrics_parses_proxy_response(app, monkeypatch):
    app.config['DOCKER_PROXY_URL'] = 'http://socket-proxy:2375'
    stats = {
        'cpu_stats': {'cpu_usage': {'total_usage': 200}, 'system_cpu_usage': 2000,
                      'online_cpus': 4},
        'memory_stats': {'usage': 1048576, 'limit': 4194304,
                         'stats': {'inactive_file': 524288}},
        'networks': {'eth0': {'rx_bytes': 100, 'tx_bytes': 50}},
    }
    responses = {
        '/containers/json?all=1': [
            {'Id': 'abc123def456789', 'Names': ['/portal'], 'Image': 'app_portal-portal',
             'State': 'running', 'Status': 'Up 2 hours'},
            {'Id': 'stopped000000000', 'Names': ['/oldapp'], 'Image': 'old',
             'State': 'exited', 'Status': 'Exited (0) 3 days ago'},
        ],
        '/stats': stats,
        '/containers/abc123def456789/json': {
            'RestartCount': 2, 'State': {'Health': {'Status': 'healthy'}}},
    }
    monkeypatch.setattr(system_metrics.urllib.request, 'urlopen',
                        _fake_urlopen_factory(responses))
    system_metrics._prev_container_cpu.clear()

    with app.app_context():
        first = system_metrics.get_container_metrics()

    running = first[0]
    assert running['name'] == 'portal'
    assert running['state'] == 'running'
    # inactive_file subtracted from memory usage
    assert running['mem_used'] == 1048576 - 524288
    assert running['mem_limit'] == 4194304
    assert running['restart_count'] == 2
    assert running['health'] == 'healthy'
    assert running['net_rx'] == 100
    # First poll has no previous sample -> no CPU % yet
    assert running['cpu_percent'] is None
    # Stopped container listed last, without stats
    assert first[1]['name'] == 'oldapp'
    assert first[1]['cpu_percent'] is None

    # Second poll: CPU delta = 200, system delta = 2000, 4 cpus -> 40%
    responses['/stats'] = {
        'cpu_stats': {'cpu_usage': {'total_usage': 400}, 'system_cpu_usage': 4000,
                      'online_cpus': 4},
        'memory_stats': {'usage': 1048576, 'limit': 4194304},
    }
    with app.app_context():
        second = system_metrics.get_container_metrics()
    assert second[0]['cpu_percent'] == 40.0


# --- Phase 2: collector + storage ---

def test_collect_metrics_cli_stores_host_sample(app):
    result = app.test_cli_runner().invoke(args=['collect-metrics'])
    assert result.exit_code == 0, result.output
    assert 'Stored 1 sample(s).' in result.output  # no docker proxy in tests
    sample = MetricSample.query.one()
    assert sample.scope == 'host'
    assert sample.cpu_pct is not None
    assert sample.mem_total > 0
    assert json.loads(sample.disk_json)
    extra = json.loads(sample.extra_json)
    assert 'load_avg' in extra and 'process_count' in extra


def test_collect_once_includes_running_containers(app, monkeypatch):
    monkeypatch.setattr(metrics_collector, 'get_container_metrics', lambda: [
        {'name': 'portal', 'state': 'running', 'cpu_percent': 12.5,
         'mem_used': 1000, 'mem_limit': 2000, 'net_rx': 1, 'net_tx': 2,
         'restart_count': 0},
        {'name': 'oldapp', 'state': 'exited', 'cpu_percent': None,
         'mem_used': None, 'mem_limit': None, 'net_rx': None, 'net_tx': None,
         'restart_count': None},
    ])
    count = metrics_collector.collect_once()
    assert count == 2  # host + running container; exited one skipped
    scopes = {s.scope for s in MetricSample.query.all()}
    assert scopes == {'host', 'portal'}
    portal = MetricSample.query.filter_by(scope='portal').one()
    assert portal.cpu_pct == 12.5
    assert portal.mem_total == 2000


def test_rollup_aggregates_min_avg_max(app):
    hour = metrics_collector._utcnow_naive().replace(
        minute=0, second=0, microsecond=0) - timedelta(hours=2)
    for i, cpu in enumerate([10.0, 20.0, 30.0]):
        _db.session.add(MetricSample(
            ts=hour + timedelta(minutes=i * 10), scope='host', cpu_pct=cpu,
            mem_used=50, mem_total=100,
            disk_json=json.dumps([{'mount': '/', 'percent': 60.0 + i}])))
    _db.session.commit()

    buckets = metrics_collector.rollup_metrics()
    assert buckets == 3  # cpu_pct, mem_pct, disk_pct:/

    cpu = MetricHourly.query.filter_by(scope='host', metric='cpu_pct').one()
    assert cpu.hour == hour
    assert (cpu.v_min, cpu.v_avg, cpu.v_max) == (10.0, 20.0, 30.0)
    mem = MetricHourly.query.filter_by(scope='host', metric='mem_pct').one()
    assert mem.v_avg == 50.0
    disk = MetricHourly.query.filter_by(scope='host', metric='disk_pct:/').one()
    assert disk.v_max == 62.0

    # Idempotent: re-running rolls up nothing new and keeps one row per metric
    assert metrics_collector.rollup_metrics() == 0
    assert MetricHourly.query.filter_by(scope='host', metric='cpu_pct').count() == 1


def test_rollup_skips_current_hour(app):
    now = metrics_collector._utcnow_naive()
    _db.session.add(MetricSample(ts=now, scope='host', cpu_pct=50.0))
    _db.session.commit()
    assert metrics_collector.rollup_metrics() == 0
    assert MetricSample.query.count() == 1  # raw sample untouched


def test_purge_metrics_boundaries(app):
    now = metrics_collector._utcnow_naive()
    _db.session.add(MetricSample(ts=now - timedelta(days=8), scope='host', cpu_pct=1.0))
    _db.session.add(MetricSample(ts=now - timedelta(hours=1), scope='host', cpu_pct=1.0))
    _db.session.add(MetricHourly(hour=now - timedelta(days=91), scope='host',
                                 metric='cpu_pct', v_min=1, v_avg=1, v_max=1))
    _db.session.add(MetricHourly(hour=now - timedelta(days=1), scope='host',
                                 metric='cpu_pct', v_min=1, v_avg=1, v_max=1))
    _db.session.commit()

    raw, hourly = metrics_collector.purge_metrics()
    assert (raw, hourly) == (1, 1)
    assert MetricSample.query.count() == 1
    assert MetricHourly.query.count() == 1


def test_purge_logs_cli(app):
    now = metrics_collector._utcnow_naive()
    _db.session.add(AccessLog(action='login', timestamp=now - timedelta(days=10)))
    _db.session.add(AccessLog(action='login', timestamp=now - timedelta(days=1)))
    _db.session.commit()

    result = app.test_cli_runner().invoke(args=['purge-logs', '--days', '5'])
    assert result.exit_code == 0, result.output
    assert 'Purged 1 access-log row(s).' in result.output
    assert AccessLog.query.count() == 1


# --- Phase 3: workload history ---

def test_workload_data_forbidden_for_normal_user(user_logged_in_client):
    resp = user_logged_in_client.get('/admin/system/workload/data')
    assert resp.status_code == 403


def _seed_raw(scope, values, minutes_ago_start=30):
    now = metrics_collector._utcnow_naive()
    for i, cpu in enumerate(values):
        _db.session.add(MetricSample(
            ts=now - timedelta(minutes=minutes_ago_start - i), scope=scope,
            cpu_pct=cpu, mem_used=cpu * 10, mem_total=1000,
            disk_json=json.dumps([{'mount': '/', 'percent': 40.0 + i}])
            if scope == 'host' else None))
    _db.session.commit()


def test_workload_data_raw_range(logged_in_client):
    _seed_raw('host', [10.0, 20.0])
    resp = logged_in_client.get(
        '/admin/system/workload/data?range=24h&scope=host&metric=cpu_pct')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['source'] == 'raw'
    (series,) = data['series']
    assert series['label'] == 'host'
    assert [p['v'] for p in series['points']] == [10.0, 20.0]
    assert series['points'][0]['t'].endswith('Z')


def test_workload_data_raw_disk_multiseries(logged_in_client):
    _seed_raw('host', [10.0, 20.0])
    resp = logged_in_client.get(
        '/admin/system/workload/data?range=1h&scope=host&metric=disk_pct')
    data = resp.get_json()
    (series,) = data['series']
    assert series['label'] == '/'
    assert [p['v'] for p in series['points']] == [40.0, 41.0]


def test_workload_data_hourly_range(logged_in_client):
    hour = metrics_collector._utcnow_naive().replace(
        minute=0, second=0, microsecond=0) - timedelta(days=2)
    _db.session.add(MetricHourly(hour=hour, scope='host', metric='cpu_pct',
                                 v_min=5.0, v_avg=15.0, v_max=25.0))
    _db.session.commit()

    resp = logged_in_client.get(
        '/admin/system/workload/data?range=7d&scope=host&metric=cpu_pct')
    data = resp.get_json()
    assert data['source'] == 'hourly'
    (series,) = data['series']
    point = series['points'][0]
    assert (point['min'], point['avg'], point['max']) == (5.0, 15.0, 25.0)


def test_workload_data_top_containers(logged_in_client):
    _seed_raw('busy-app', [90.0, 95.0])
    _seed_raw('quiet-app', [1.0, 2.0])
    resp = logged_in_client.get(
        '/admin/system/workload/data?range=24h&scope=containers&metric=cpu_pct')
    data = resp.get_json()
    labels = [s['label'] for s in data['series']]
    assert set(labels) == {'busy-app', 'quiet-app'}
    assert labels == sorted(labels)  # alphabetical for stable colors


def test_workload_data_rejects_bad_params(logged_in_client):
    assert logged_in_client.get(
        '/admin/system/workload/data?range=5y').status_code == 400
    assert logged_in_client.get(
        '/admin/system/workload/data?metric=bogus').status_code == 400
    assert logged_in_client.get(
        '/admin/system/workload/data?scope=portal&metric=disk_pct').status_code == 400


# --- Phase 4: per-app usage analytics ---

def _seed_access_logs(db, users, apps):
    """Seed a small known set of usage events."""
    admin, normal = users
    app1, app2 = apps[0], apps[1]
    now = metrics_collector._utcnow_naive()
    rows = [
        (admin.id, app1.id, 'access_app', now - timedelta(days=1)),
        (admin.id, app1.id, 'access_app', now - timedelta(hours=2)),
        (normal.id, app1.id, 'validate', now - timedelta(hours=1)),
        (normal.id, app2.id, 'access_app', now - timedelta(days=10)),
        (normal.id, app2.id, 'denied', now - timedelta(hours=3)),
        (admin.id, None, 'login', now - timedelta(hours=4)),  # not app-bound
    ]
    for user_id, app_id, action, ts in rows:
        db.session.add(AccessLog(user_id=user_id, app_id=app_id, action=action,
                                 timestamp=ts, ip_address='10.0.0.1'))
    db.session.commit()
    return app1, app2


def test_validate_token_logs_validate(client, normal_user, sample_app, db):
    from app.services.token_service import generate_token
    perm = __import__('app.models.permission', fromlist=['UserPermission']).UserPermission(
        user_id=normal_user.id, app_id=sample_app.id)
    db.session.add(perm)
    db.session.commit()
    token = generate_token(normal_user.id)

    resp = client.post('/api/validate-token',
                       json={'token': token, 'app_code': 'testapp'})
    assert resp.status_code == 200

    log = AccessLog.query.filter_by(action='validate').one()
    assert log.user_id == normal_user.id
    assert log.app_id == sample_app.id
    assert token not in (log.details or '')


def test_validate_token_denied_is_logged(client, normal_user, sample_app):
    from app.services.token_service import generate_token
    token = generate_token(normal_user.id)  # no permission granted

    resp = client.post('/api/validate-token',
                       json={'token': token, 'app_code': 'testapp'})
    assert resp.status_code == 403

    log = AccessLog.query.filter_by(action='denied').one()
    assert log.user_id == normal_user.id
    assert log.app_id == sample_app.id
    assert token not in (log.details or '')


def test_usage_data_forbidden_for_normal_user(user_logged_in_client):
    assert user_logged_in_client.get('/admin/system/usage/data').status_code == 403
    assert user_logged_in_client.get('/admin/system/usage/export.csv').status_code == 403


def test_usage_summary_aggregation(logged_in_client, db, admin_user, normal_user, sample_apps):
    app1, app2 = _seed_access_logs(db, (admin_user, normal_user), sample_apps)

    resp = logged_in_client.get('/admin/system/usage/data')
    assert resp.status_code == 200
    summary = {r['app_name']: r for r in resp.get_json()['summary']}

    r1 = summary[app1.app_name]
    assert (r1['access_app'], r1['validate'], r1['denied']) == (2, 1, 0)
    assert r1['unique_users'] == 2
    r2 = summary[app2.app_name]
    assert (r2['access_app'], r2['denied']) == (1, 1)
    # busiest app first
    assert resp.get_json()['summary'][0]['app_name'] == app1.app_name


def test_usage_filters_by_date_and_user(logged_in_client, db, admin_user, normal_user, sample_apps):
    app1, app2 = _seed_access_logs(db, (admin_user, normal_user), sample_apps)
    start = (metrics_collector._utcnow_naive() - timedelta(days=2)).strftime('%Y-%m-%d')

    resp = logged_in_client.get(f'/admin/system/usage/data?start={start}')
    names = [r['app_name'] for r in resp.get_json()['summary']]
    r2 = [r for r in resp.get_json()['summary'] if r['app_name'] == app2.app_name][0]
    assert r2['access_app'] == 0  # 10-day-old launch filtered out
    assert r2['denied'] == 1

    resp = logged_in_client.get(f'/admin/system/usage/data?user_id={normal_user.id}')
    summary = {r['app_name']: r for r in resp.get_json()['summary']}
    assert summary[app1.app_name]['access_app'] == 0
    assert summary[app1.app_name]['validate'] == 1


def test_usage_page_renders_tables(logged_in_client, db, admin_user, normal_user, sample_apps):
    _seed_access_logs(db, (admin_user, normal_user), sample_apps)
    resp = logged_in_client.get('/admin/system/usage')
    html = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert 'Per-App Summary' in html
    assert 'Per-User Detail' in html
    assert 'Export CSV' in html


def test_usage_csv_export(logged_in_client, db, admin_user, normal_user, sample_apps):
    _seed_access_logs(db, (admin_user, normal_user), sample_apps)
    resp = logged_in_client.get('/admin/system/usage/export.csv')
    assert resp.status_code == 200
    assert resp.mimetype == 'text/csv'
    lines = resp.get_data(as_text=True).strip().splitlines()
    assert lines[0] == 'timestamp,user,action,application,ip_address,details'
    # header + all log rows (6 seeded + the fixture admin's own login event)
    assert len(lines) == 1 + AccessLog.query.count()
    assert any('testuser,denied,' in line for line in lines)


def test_usage_csv_export_row_cap(logged_in_client, db, admin_user, normal_user,
                                  sample_apps, app):
    _seed_access_logs(db, (admin_user, normal_user), sample_apps)
    app.config['USAGE_EXPORT_MAX_ROWS'] = 2
    resp = logged_in_client.get('/admin/system/usage/export.csv')
    lines = resp.get_data(as_text=True).strip().splitlines()
    assert len(lines) == 3  # header + capped rows
