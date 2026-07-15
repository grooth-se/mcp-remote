import json
import os
import time
import urllib.error
import urllib.request

import psutil
from flask import current_app

# Previous one-shot Docker stats per container id, kept so CPU % can be
# computed as a delta between successive polls (one-shot stats have no precpu).
_prev_container_cpu = {}


def _apply_host_procfs():
    """Point psutil at the host's /proc when running in the collector
    container (HOST_PROC=/host/proc). No-op in the portal container."""
    host_proc = os.environ.get('HOST_PROC')
    if host_proc and psutil.PROCFS_PATH != host_proc:
        psutil.PROCFS_PATH = host_proc


def get_host_metrics(cpu_interval=None):
    """Snapshot of host-level metrics via psutil.

    With cpu_interval=None, cpu_percent measures since the previous call in
    this process (matches a fixed polling/sampling interval); pass a small
    interval for one-shot invocations where no previous call exists.
    """
    _apply_host_procfs()
    vm = psutil.virtual_memory()
    swap = psutil.swap_memory()

    try:
        load1, load5, load15 = psutil.getloadavg()
    except OSError:
        load1 = load5 = load15 = None

    disks = []
    host_root = os.environ.get('HOST_ROOT')
    if host_root:
        # Collector container: measure the host's root fs via its ro mount.
        try:
            usage = psutil.disk_usage(host_root)
            disks.append({'mount': '/', 'total': usage.total, 'used': usage.used,
                          'free': usage.free, 'percent': usage.percent})
        except OSError:
            pass
    else:
        seen_devices = set()
        for part in psutil.disk_partitions(all=False):
            if part.device in seen_devices:
                continue
            try:
                usage = psutil.disk_usage(part.mountpoint)
            except (PermissionError, OSError):
                continue
            seen_devices.add(part.device)
            disks.append({
                'mount': part.mountpoint,
                'total': usage.total,
                'used': usage.used,
                'free': usage.free,
                'percent': usage.percent,
            })

    try:
        dio = psutil.disk_io_counters()
        disk_io = {'read_bytes': dio.read_bytes, 'write_bytes': dio.write_bytes} if dio else None
    except (RuntimeError, OSError):
        disk_io = None
    try:
        nio = psutil.net_io_counters()
        net_io = {'bytes_sent': nio.bytes_sent, 'bytes_recv': nio.bytes_recv}
    except (RuntimeError, OSError):
        net_io = None

    boot_time = psutil.boot_time()
    return {
        'cpu_percent': psutil.cpu_percent(interval=cpu_interval),
        'cpu_percent_per_core': psutil.cpu_percent(interval=None, percpu=True),
        'cpu_count': psutil.cpu_count(),
        'load_avg': {'1m': load1, '5m': load5, '15m': load15},
        'memory': {
            'total': vm.total,
            'used': vm.used,
            'available': vm.available,
            'percent': vm.percent,
        },
        'swap': {'total': swap.total, 'used': swap.used, 'percent': swap.percent},
        'disks': disks,
        'disk_io': disk_io,
        'net_io': net_io,
        'boot_time': boot_time,
        'uptime_seconds': int(time.time() - boot_time),
        'process_count': len(psutil.pids()),
    }


def _proxy_get(path, timeout):
    base = current_app.config.get('DOCKER_PROXY_URL', '').rstrip('/')
    req = urllib.request.Request(base + path, method='GET')
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode('utf-8'))


def _container_cpu_percent(container_id, stats):
    """CPU % from one-shot stats, as a delta against the previous poll."""
    cpu = stats.get('cpu_stats', {})
    total = cpu.get('cpu_usage', {}).get('total_usage')
    system = cpu.get('system_cpu_usage')
    online_cpus = cpu.get('online_cpus') or 1
    now = time.monotonic()

    prev = _prev_container_cpu.get(container_id)
    _prev_container_cpu[container_id] = {'total': total, 'system': system, 'ts': now}
    if not prev or total is None or system is None \
            or prev['total'] is None or prev['system'] is None:
        return None
    cpu_delta = total - prev['total']
    system_delta = system - prev['system']
    if system_delta <= 0 or cpu_delta < 0:
        return None
    return round((cpu_delta / system_delta) * online_cpus * 100.0, 1)


def get_container_metrics():
    """Per-container stats via the read-only docker-socket-proxy.

    Returns None when no proxy is configured (section hidden in the UI),
    or {'error': ...} when the proxy is configured but unreachable.
    """
    if not current_app.config.get('DOCKER_PROXY_URL'):
        return None
    timeout = current_app.config.get('HEALTH_CHECK_TIMEOUT', 3)

    try:
        containers = _proxy_get('/containers/json?all=1', timeout)
    except (urllib.error.URLError, OSError, ValueError) as e:
        return {'error': f'Docker proxy unreachable: {e}'}

    results = []
    for c in containers:
        entry = {
            'id': c.get('Id', '')[:12],
            'name': (c.get('Names') or ['?'])[0].lstrip('/'),
            'image': c.get('Image'),
            'state': c.get('State'),
            'status': c.get('Status'),
            'cpu_percent': None,
            'mem_used': None,
            'mem_limit': None,
            'net_rx': None,
            'net_tx': None,
            'restart_count': None,
        }
        if c.get('State') == 'running':
            try:
                stats = _proxy_get(
                    f"/containers/{c['Id']}/stats?stream=false&one-shot=true", timeout)
                entry['cpu_percent'] = _container_cpu_percent(c['Id'], stats)
                mem = stats.get('memory_stats', {})
                usage = mem.get('usage')
                if usage is not None:
                    # Subtract page cache the kernel can reclaim (cgroup v2)
                    usage -= mem.get('stats', {}).get('inactive_file', 0)
                entry['mem_used'] = usage
                entry['mem_limit'] = mem.get('limit')
                networks = stats.get('networks') or {}
                if networks:
                    entry['net_rx'] = sum(n.get('rx_bytes', 0) for n in networks.values())
                    entry['net_tx'] = sum(n.get('tx_bytes', 0) for n in networks.values())
            except (urllib.error.URLError, OSError, ValueError, KeyError):
                pass
            try:
                inspect = _proxy_get(f"/containers/{c['Id']}/json", timeout)
                entry['restart_count'] = inspect.get('RestartCount')
                health = inspect.get('State', {}).get('Health')
                if health:
                    entry['health'] = health.get('Status')
            except (urllib.error.URLError, OSError, ValueError, KeyError):
                pass
        results.append(entry)
    results.sort(key=lambda r: (r['state'] != 'running', r['name']))
    return results
