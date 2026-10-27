"""Check team HTTP health endpoints. Python 3; no external packages."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sqlite3
import time
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def save_results(database, checked_at, results):
    """Commit the complete check cycle atomically; never clear older results."""
    with closing(sqlite3.connect(database, timeout=10)) as connection, connection:
        connection.execute('PRAGMA foreign_keys = ON')
        connection.execute('''CREATE TABLE IF NOT EXISTS check_cycles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            checked_at TEXT NOT NULL)''')
        connection.execute('''CREATE TABLE IF NOT EXISTS check_results (
            cycle_id INTEGER NOT NULL REFERENCES check_cycles(id),
            name TEXT NOT NULL, url TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('UP', 'DOWN')),
            elapsed_ms INTEGER NOT NULL, detail TEXT NOT NULL,
            PRIMARY KEY (cycle_id, name))''')
        cycle_id = connection.execute(
            'INSERT INTO check_cycles (checked_at) VALUES (?)', (checked_at,)).lastrowid
        connection.executemany(
            'INSERT INTO check_results VALUES (?, ?, ?, ?, ?, ?)',
            [(cycle_id, r['name'], r['url'], r['status'], r['elapsed_ms'], r['detail'])
             for r in results])
    return cycle_id


def check_web(target, timeout):
    started = time.monotonic()
    result = {'name': target['name'], 'url': target['url'], 'status': 'DOWN'}
    try:
        opener = build_opener(ProxyHandler({}), NoRedirect())
        with opener.open(Request(target['url'], headers={'Accept': 'application/json'}),
                         timeout=timeout) as response:
            if response.status != 200:
                raise ValueError('Expected HTTP 200')
            body = response.read(65537)
            if len(body) > 65536:
                raise ValueError('Health response too large')
            health = json.loads(body)
            if not isinstance(health, dict) or health.get('status') != 'ok':
                raise ValueError('Expected JSON status=ok')
            if target.get('expected_sandbox') and health.get('sandbox') != target['expected_sandbox']:
                raise ValueError('Wrong sandbox identity')
            if target.get('expected_node') and health.get('node') != target['expected_node']:
                raise ValueError('Wrong node identity')
        result['status'] = 'UP'
        result['detail'] = 'HTTP 200, status=ok'
    except Exception as exc:
        result['detail'] = type(exc).__name__ + ': ' + str(exc)
    result['elapsed_ms'] = round((time.monotonic() - started) * 1000)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default='web_targets.json')
    parser.add_argument('--timeout', type=float, default=3)
    parser.add_argument('--interval', type=float, default=0,
                        help='Seconds between checks; 0 runs once')
    parser.add_argument('--json', action='store_true', help='Output JSON per round')
    parser.add_argument('--database', help='SQLite file for durable check history')
    args = parser.parse_args()
    if not math.isfinite(args.timeout) or not math.isfinite(args.interval) or args.timeout <= 0 or args.interval < 0:
        parser.error('timeout must be positive; interval must be nonnegative')
    with open(args.config, encoding='utf-8-sig') as stream:
        targets = json.load(stream)['targets']
    if not targets or any(not t.get('name') or not t.get('url', '').startswith(('http://', 'https://')) for t in targets):
        parser.error('config needs named targets with HTTP(S) URLs')
    if len({t['name'] for t in targets}) != len(targets):
        parser.error('target names must be unique')
    if args.database and not Path(args.database).parent.is_dir():
        parser.error('database parent directory must exist')
    try:
        while True:
            started = time.monotonic()
            with ThreadPoolExecutor(max_workers=min(len(targets), 4)) as executor:
                results = list(executor.map(lambda t: check_web(t, args.timeout), targets))
            checked_at = datetime.now(timezone.utc).isoformat(timespec='seconds')
            cycle_id = save_results(args.database, checked_at, results) if args.database else None
            if args.json:
                print(json.dumps({'cycle_id': cycle_id, 'checked_at': checked_at, 'results': results}), flush=True)
            else:
                print('\nChecked at ' + checked_at, flush=True)
                for row in results:
                    print(f"{row['name']:<12} {row['status']:<5} {row['elapsed_ms']:>5} ms  {row['url']}  {row['detail']}", flush=True)
            if not args.interval:
                return 0 if all(r['status'] == 'UP' for r in results) else 1
            # Measure the interval between round starts, including request time.
            time.sleep(max(0, args.interval - (time.monotonic() - started)))
    except KeyboardInterrupt:
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
