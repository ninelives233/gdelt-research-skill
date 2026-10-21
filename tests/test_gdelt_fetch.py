import importlib.util
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

SCRIPT = str(Path(__file__).resolve().parents[1] / 'gdelt-research/scripts/gdelt_fetch.py')
spec = importlib.util.spec_from_file_location('gdelt_fetch', SCRIPT)
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)


class FakeClient:
    def __init__(self, out, responses):
        self.out = out
        self.responses = iter(responses)
        self.calls = []

    def get_json(self, params):
        self.calls.append(params)
        result = next(self.responses)
        if isinstance(result, Exception):
            raise result
        return result


def article(url, timestamp):
    return {'url': url, 'seendate': timestamp, 'title': 'sample'}


class FetchTests(unittest.TestCase):
    def run_doc(self, responses, sample=False, end='20180706010000'):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        client = FakeClient(Path(temp.name), responses)
        args = SimpleNamespace(start='20180706000000', end=end, sample=sample, query='China', max_records=2)
        manifest = {}
        g.doc(args, client, manifest)
        return client, manifest

    def test_split_deduplicates_shared_urls(self):
        a = article('https://a', '20180706T000100Z')
        b = article('https://b', '20180706T003100Z')
        client, m = self.run_doc([{'articles': [a, b]}, {'articles': [a]}, {'articles': [b]}])
        self.assertEqual(m['exported_rows'], 2)
        self.assertEqual(len(client.calls), 3)
        self.assertEqual(m['completeness'], 'no_observed_cap')

    def test_minimum_window_reports_cap(self):
        _, m = self.run_doc([{'articles': [article('a', '20180706T000100Z'), article('b', '20180706T000200Z')]}], end='20180706001500')
        self.assertEqual(m['completeness'], 'incomplete_capped_windows')
        self.assertEqual(len(m['unresolved_windows']), 1)

    def test_sample_never_claims_complete(self):
        client, m = self.run_doc([{'articles': [article('a', '20180706T000100Z'), article('b', '20180706T000200Z')]}], sample=True)
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(m['completeness'], 'sample_only')

    def test_exclusive_end_and_outside_dates(self):
        _, m = self.run_doc([{'articles': [article('a', '20180706T000100Z'), article('b', '20180706T010000Z')]}], sample=True)
        self.assertEqual(m['exported_rows'], 1)
        self.assertEqual(m['windows'][0]['outside_requested_window'], 1)

    def test_empty_result_is_valid(self):
        _, m = self.run_doc([{'articles': []}])
        self.assertEqual(m['exported_rows'], 0)
        self.assertEqual(m['completeness'], 'no_observed_cap')

    def test_missing_schema_is_error(self):
        with self.assertRaisesRegex(RuntimeError, 'Missing articles'):
            self.run_doc([{}])

    def test_failure_preserves_completed_rows_and_pending_range(self):
        with tempfile.TemporaryDirectory() as d:
            a = article('a', '20180706T000100Z')
            b = article('b', '20180706T003100Z')
            client = FakeClient(Path(d), [{'articles': [a, b]}, RuntimeError('HTTP 429')])
            m = {}
            args = SimpleNamespace(start='20180706000000', end='20180706010000', sample=False, query='China', max_records=2)
            with self.assertRaisesRegex(RuntimeError, '429'):
                g.doc(args, client, m)
            self.assertEqual(m['exported_rows'], 2)
            self.assertEqual(len(m['pending_windows']), 2)
            self.assertTrue((Path(d) / 'articles.csv').exists())

    def test_csv_preserves_code_and_multiline_title(self):
        import csv
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'values.csv'
            g.write_csv(p, [{'code': '010', 'title': '标题,"quoted"\nnext'}], ['code', 'title'])
            with p.open(encoding='utf-8-sig', newline='') as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(rows[0]['code'], '010')
            self.assertEqual(rows[0]['title'], '标题,"quoted"\nnext')

    def test_rate_limit_at_budget_stops_without_retry_wait(self):
        from unittest.mock import patch
        def limited_curl(argv, **kwargs):
            Path(argv[argv.index('--output') + 1]).write_text('Please limit requests to one every 5 seconds')
            Path(argv[argv.index('--dump-header') + 1]).write_text('HTTP/1.1 429 Too Many Requests\n')
            return SimpleNamespace(stdout='429', stderr='', returncode=0)
        with tempfile.TemporaryDirectory() as d:
            client = g.Client(Path(d) / 'download', max_requests=1)
            with patch.object(g.subprocess, 'run', side_effect=limited_curl), patch.object(g.time, 'sleep') as sleep:
                with self.assertRaisesRegex(RuntimeError, 'HTTP 429'):
                    client.get('https://api.gdeltproject.org/example', '.json')
                self.assertTrue(all(call.args[0] <= 6 for call in sleep.call_args_list))
            self.assertEqual(len(client.log), 1)
            self.assertTrue(client.log[0]['rate_limited'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
