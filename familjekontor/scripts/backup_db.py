#!/usr/bin/env python3
"""Database backup using pg_dump."""

import os
import subprocess
from datetime import datetime


def main():
    db_url = os.environ.get('DATABASE_URL', 'postgresql://psalmgears:psalmgears@localhost:5432/psalmgears')

    backup_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'backups')
    os.makedirs(backup_dir, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'psalmgears_backup_{timestamp}.sql'
    filepath = os.path.join(backup_dir, filename)

    # Parse connection string
    parts = db_url.replace('postgresql://', '').split('@')
    user_pass = parts[0].split(':')
    host_db = parts[1].split('/')

    env = os.environ.copy()
    env['PGPASSWORD'] = user_pass[1]

    host_port = host_db[0].split(':')

    cmd = [
        'pg_dump',
        '-h', host_port[0],
        '-p', host_port[1] if len(host_port) > 1 else '5432',
        '-U', user_pass[0],
        '-d', host_db[1],
        '-f', filepath,
        '--format=plain',
    ]

    print(f'Running backup: {filename}')
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)

    if result.returncode == 0:
        size = os.path.getsize(filepath)
        print(f'Backup complete: {filepath} ({size} bytes)')
    else:
        print(f'Backup failed: {result.stderr}')


if __name__ == '__main__':
    main()
