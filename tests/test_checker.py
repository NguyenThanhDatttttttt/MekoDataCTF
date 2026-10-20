import importlib.util
import json
from pathlib import Path
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('web_health', ROOT / 'checker/web_health.py')
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class CheckerTests(unittest.TestCase):
    def test_health_failures_and_recovery_over_http(self):
        class Handler(BaseHTTPRequestHandler):
            payload = b'{"status":"ok","node":"attacker1"}'
            code = 200

            def do_GET(self):
                self.send_response(self.code)
                self.end_headers()
                self.wfile.write(self.payload)

            def log_message(self, *args):
                pass

        with ThreadingHTTPServer(('127.0.0.1', 0), Handler) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            target = {'name': 'team01', 'url': f'http://127.0.0.1:{server.server_port}/health',
                      'expected_node': 'attacker1'}
            try:
                self.assertEqual(checker.check_web(target, 1)['status'], 'UP')
                for payload, code in [(b'not json', 200), (b'{"status":"down"}', 200),
                                      (b'{"status":"ok","node":"attacker2"}', 200),
                                      (b'x' * 65537, 200), (b'{}', 503), (b'{}', 302)]:
                    Handler.payload, Handler.code = payload, code
                    self.assertEqual(checker.check_web(target, 1)['status'], 'DOWN')
                Handler.payload = b'{"status":"ok","node":"attacker1"}'
                Handler.code = 200
                self.assertEqual(checker.check_web(target, 1)['status'], 'UP')
            finally:
                server.shutdown()
                thread.join(3)
        self.assertEqual(checker.check_web(target, 0.1)['status'], 'DOWN')

    def test_round_interval_includes_check_duration(self):
        config = ROOT / 'checker/web_targets.json'
        with patch('sys.argv', ['web_health.py', '--config', str(config), '--interval', '30', '--json']), \
             patch.object(checker, 'check_web', return_value={'status': 'DOWN'}), \
             patch.object(checker.time, 'monotonic', side_effect=[100, 103]), \
             patch.object(checker.time, 'sleep', side_effect=KeyboardInterrupt) as sleep, \
             patch('builtins.print'):
            self.assertEqual(checker.main(), 130)
            sleep.assert_called_once_with(27)

    def test_one_shot_exit_code(self):
        config = ROOT / 'checker/web_targets.json'
        for status, expected in [('UP', 0), ('DOWN', 1)]:
            with patch('sys.argv', ['web_health.py', '--config', str(config), '--json']), \
                 patch.object(checker, 'check_web', return_value={'status': status}), \
                 patch('builtins.print'):
                self.assertEqual(checker.main(), expected)


if __name__ == '__main__':
    unittest.main()
