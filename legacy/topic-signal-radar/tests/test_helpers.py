import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import check_env
import save_run


def bundle(url='https://example.com/post?id=1', tool='last30days-skill-cn'):
    return {'tool': tool, 'version': None, 'channels': [{'platform': 'test', 'status': 'success', 'path': 'web', 'reason': ''}], 'evidence': [{'url': url, 'platform': 'test', 'title': '标题', 'summary': '仅搜索摘要', 'published_at': None, 'date_confidence': 'unknown', 'metrics': None, 'path': 'web', 'access': 'link'}]}


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.run = save_run.init('主题', 'both', output=self.root / 'out')

    def tearDown(self):
        self.temp.cleanup()

    def add(self, data):
        p = self.root / 'bundle.json'
        p.write_text(json.dumps(data), encoding='utf-8')
        return save_run.ingest(self.run, p)

    def test_historical_window(self):
        run = save_run.init('主题', 'cn', days=7, output=self.root / 'out', as_of='2026-10-01')
        task = json.loads((run / 'task.json').read_text())
        self.assertEqual(task['from_date'], '2026-09-24')
        self.assertEqual(task['to_date'], '2026-10-01')

    def test_real_cn_export_archives_without_changing_schema(self):
        source = Path(__file__).parent / 'fixtures/cn-report-excerpt.json'
        b = bundle(); b['raw_files'] = [str(source)]
        batch = self.add(b)
        saved = json.loads((batch / 'bundle.json').read_text())
        self.assertEqual((batch / saved['raw_files'][0]['file']).read_bytes(), source.read_bytes())
        self.assertIn('bvid', json.loads(source.read_text())['bilibili'][0])

    def test_capture_time_is_not_fabricated_from_archive_time(self):
        self.add(bundle())
        observation = save_run.aggregate(self.run)['evidence'][0]['observations'][0]
        self.assertIsNone(observation['retrieved_at'])
        self.assertIsNotNone(observation['archived_at'])

    def test_verified_capture_time_survives(self):
        b = bundle(); b['retrieved_at'] = '2026-10-24T01:00:00+08:00'
        self.add(b)
        self.assertEqual(save_run.aggregate(self.run)['evidence'][0]['observations'][0]['retrieved_at'], b['retrieved_at'])

    def test_run_isolation(self):
        other = save_run.init('主题', 'both', output=self.root / 'out')
        self.assertNotEqual(other, self.run)

    def test_exact_duplicate_keeps_all_observations(self):
        self.add(bundle())
        self.add(bundle(tool='Agent-Reach'))
        data = save_run.aggregate(self.run)
        self.assertEqual(len(data['evidence']), 1)
        self.assertEqual(len(data['evidence'][0]['observations']), 2)
        self.assertEqual({x['tool'] for x in data['evidence'][0]['observations']}, {'Agent-Reach', 'last30days-skill-cn'})

    def test_query_parameters_preserved(self):
        self.add(bundle('https://example.com/post?id=1&xsec_token=abc'))
        self.add(bundle('https://example.com/post?id=1&xsec_token=def'))
        self.assertEqual(len(save_run.aggregate(self.run)['evidence']), 2)

    def test_unknown_values_not_zero(self):
        self.add(bundle())
        observation = save_run.aggregate(self.run)['evidence'][0]['observations'][0]
        self.assertIsNone(observation['metrics'])
        self.assertIsNone(observation['published_at'])

    def test_invalid_evidence_is_atomic(self):
        b = bundle(); b['evidence'][0]['metrics'] = {'likes': -1}
        with self.assertRaises(ValueError): self.add(b)
        self.assertEqual(list((self.run / 'batches').iterdir()), [])

    def test_malformed_exports_rejected(self):
        for name, content in [('bad.json', '{'), ('bad.jsonl', '{}\nnot-json'), ('bad.csv', 'a,b\n1,2,3')]:
            p = self.root / name; p.write_text(content)
            b = bundle(); b['raw_files'] = [str(p)]
            with self.assertRaises(ValueError): self.add(b)
        self.assertEqual(list((self.run / 'batches').iterdir()), [])

    def test_raw_copy_and_checksum(self):
        p = self.root / 'source.json'; p.write_text('{"items": []}')
        b = bundle(); b['raw_files'] = ['source.json']
        batch = self.add(b)
        p.write_text('{"items": [1]}')
        saved = json.loads((batch / 'bundle.json').read_text())
        archived = batch / saved['raw_files'][0]['file']
        self.assertEqual(archived.read_text(), '{"items": []}')
        self.assertEqual(len(saved['raw_files'][0]['sha256']), 64)

    def test_partial_failures_survive_finalize(self):
        b = bundle(); b['channels'].append({'platform': 'xhs', 'status': 'need_login', 'path': 'browser', 'reason': '没有已保存会话'})
        self.add(b)
        eid = save_run.aggregate(self.run)['evidence'][0]['id']
        brief = self.root / 'brief.md'; brief.write_text('有材料 [%s]，其他平台缺失。' % eid)
        final = save_run.finalize(self.run, brief)
        self.assertIn('need_login', (final / 'report.md').read_text())
        with self.assertRaises(ValueError): self.add(bundle())

    def test_cards_require_real_evidence(self):
        self.add(bundle())
        brief = self.root / 'brief.md'; eid = save_run.aggregate(self.run)['evidence'][0]['id']; brief.write_text('[%s]' % eid)
        cards = self.root / 'cards.json'
        card = {k: '说明' for k in ['audience', 'context', 'problem', 'workaround', 'to_verify']}
        card.update(supporting=['E0000000000000000'], opposing=[])
        cards.write_text(json.dumps([card]))
        with self.assertRaises(ValueError): save_run.finalize(self.run, brief, cards)
        self.assertFalse((self.run / 'final').exists())
        card['supporting'] = [eid]; cards.write_text(json.dumps([card]))
        self.assertTrue((save_run.finalize(self.run, brief, cards) / 'signal-cards.json').exists())

    def test_finalized_run_remains_readable(self):
        self.add(bundle())
        eid = save_run.aggregate(self.run)['evidence'][0]['id']
        brief = self.root / 'brief.md'; brief.write_text('[%s]' % eid)
        save_run.finalize(self.run, brief)
        self.assertEqual(save_run.run_dir(self.run, writable=False), self.run)
        self.assertEqual(len(save_run.aggregate(self.run)['evidence']), 1)
        with self.assertRaises(ValueError): save_run.run_dir(self.run)

    def test_retired_source_rejected_without_rewriting_history(self):
        b = bundle(tool='x-mcp')
        with self.assertRaises(ValueError): self.add(b)
        self.assertEqual(list((self.run / 'batches').iterdir()), [])
        batch = self.add(bundle())
        p = batch / 'bundle.json'
        archived = json.loads(p.read_text())
        archived['tool'] = 'x-mcp'
        original = json.dumps(archived)
        p.write_text(original)
        self.assertEqual(save_run.aggregate(self.run)['runs'][0]['tool'], 'x-mcp')
        self.assertEqual(p.read_text(), original)

    def test_unknown_brief_reference_rejected(self):
        brief = self.root / 'brief.md'; brief.write_text('[E0000000000000000]')
        with self.assertRaises(ValueError): save_run.finalize(self.run, brief)

    def test_credential_url_rejected(self):
        with self.assertRaises(ValueError): self.add(bundle('https://user:secret@example.com/'))

    def test_credential_file_rejected(self):
        p = self.root / 'cookies.json'; p.write_text('{}')
        b = bundle(); b['raw_files'] = [str(p)]
        with self.assertRaises(ValueError): self.add(b)


class StatusTests(unittest.TestCase):
    def test_no_network_in_default_check(self):
        with patch.object(check_env, 'get_json', side_effect=AssertionError('must not connect')):
            data = check_env.inspect(selected=['xiaohongshu-mcp'])
        self.assertEqual(data['projects'][0]['login'], 'unknown')
        self.assertEqual(data['projects'][0]['request'], 'unknown')

    def test_reachable_not_logged_in(self):
        with patch.object(check_env, 'get_json', side_effect=[{'success': True}, {'data': {'is_logged_in': False}}]):
            status = check_env.probe_xhs('http://localhost:18060')
        self.assertEqual(status['service'], 'reachable')
        self.assertEqual(status['login'], 'missing')

    def test_network_failure_not_need_login(self):
        with patch.object(check_env, 'get_json', side_effect=OSError('secret must not leak')):
            status = check_env.probe_xhs('http://localhost:18060')
        self.assertEqual(status['login'], 'unknown')
        self.assertNotIn('secret', str(status))

    def test_login_success_not_request_success(self):
        with patch.object(check_env, 'get_json', side_effect=[{'success': True}, {'data': {'is_logged_in': True}}]):
            data = check_env.inspect(probe=True, selected=['xiaohongshu-mcp'])
        self.assertEqual(data['projects'][0]['login'], 'valid')
        self.assertEqual(data['projects'][0]['request'], 'unknown')

    def test_source_missing_does_not_claim_ready(self):
        with tempfile.TemporaryDirectory() as folder:
            data = check_env.inspect({'social-media-copilot': {'path': folder + '/missing'}}, selected=['social-media-copilot'])
        self.assertFalse(data['projects'][0]['source_exists'])
        self.assertFalse(data['projects'][0]['entry_exists'])
        self.assertEqual(data['projects'][0]['dependencies'], 'unknown')

    def test_retired_project_config_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / 'local.json'
            p.write_text('{"projects":{"x-mcp":{"path":"unused"}}}')
            with self.assertRaises(ValueError): check_env.load_config(p)

    def test_secret_config_and_url_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / 'local.json'
            p.write_text('{"projects":{"social-media-copilot":{"token":"secret"}}}')
            with self.assertRaises(ValueError): check_env.load_config(p)
        with self.assertRaises(ValueError): check_env.service_url('https://example.com/?key=secret')


if __name__ == '__main__':
    unittest.main()
