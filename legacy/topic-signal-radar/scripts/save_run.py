#!/usr/bin/env python3
"""Append evidence batches and finalize a traceable research folder. No collection."""
import argparse
import csv
from datetime import date, datetime, timezone, timedelta
import hashlib
import io
import json
import math
from pathlib import Path
import re
import shutil
import tempfile
import uuid
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
TOOLS = {'last30days-skill', 'last30days-skill-cn', 'Agent-Reach', 'MediaCrawler', 'social-media-copilot', 'xiaohongshu-mcp', 'goofish-cli', 'ai-goofish-monitor', 'host-web'}
STATES = {'success', 'empty', 'missing_dependency', 'need_login', 'blocked', 'rate_limited', 'timeout', 'error', 'degraded', 'unknown'}
ACCESS = {'link', 'body', 'comments', 'product', 'monitor_result'}
CST = timezone(timedelta(hours=8))


def dump(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def text(value, name, empty=False):
    if not isinstance(value, str) or (not value.strip() and not empty):
        raise ValueError(name + ' 必须是字符串' + ('' if empty else '且非空'))
    return value


def object_keys(value, required, allowed, name):
    if not isinstance(value, dict) or not set(required) <= set(value) or set(value) - set(allowed):
        raise ValueError(name + ' 字段错误')


def safe_url(url):
    text(url, 'url')
    p = urlsplit(url)
    if p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password:
        raise ValueError('证据链接必须是无内嵌凭据的 HTTP(S) 链接')
    return url  # Keep the entire query and fragment. Never guess tracking parameters.


def timestamp(value):
    if value is not None:
        text(value, 'published_at')
        try:
            datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            date.fromisoformat(value)
    return value


def validate_bundle(bundle):
    object_keys(bundle, ['tool', 'version', 'channels', 'evidence'], ['tool', 'version', 'channels', 'evidence', 'raw_files', 'retrieved_at'], 'bundle')
    if bundle['tool'] not in TOOLS:
        raise ValueError('未知工具')
    if bundle['version'] is not None:
        text(bundle['version'], 'version')
    if not isinstance(bundle['channels'], list) or not isinstance(bundle['evidence'], list):
        raise ValueError('channels / evidence 必须是数组')
    for channel in bundle['channels']:
        object_keys(channel, ['platform', 'status', 'path', 'reason'], ['platform', 'status', 'path', 'reason'], 'channel')
        if channel['status'] not in STATES:
            raise ValueError('未知渠道状态')
        for key in ('platform', 'path', 'reason'):
            text(channel[key], key, empty=key == 'reason')
    for item in bundle['evidence']:
        object_keys(item, ['url', 'platform', 'title', 'summary', 'published_at', 'date_confidence', 'metrics', 'path', 'access'],
                    ['url', 'platform', 'title', 'summary', 'published_at', 'date_confidence', 'metrics', 'path', 'access'], 'evidence')
        safe_url(item['url'])
        for key in ('platform', 'title', 'path'):
            text(item[key], key)
        text(item['summary'], 'summary', empty=True)
        timestamp(item['published_at'])
        if item['date_confidence'] not in ('high', 'medium', 'low', 'unknown') or item['access'] not in ACCESS:
            raise ValueError('日期可信度或读取深度错误')
        if item['published_at'] is None and item['date_confidence'] != 'unknown':
            raise ValueError('未知发布时间必须标记 unknown')
        if item['metrics'] is not None:
            if not isinstance(item['metrics'], dict):
                raise ValueError('metrics 必须是对象或 null')
            for key, value in item['metrics'].items():
                text(key, 'metric name')
                if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0 or not math.isfinite(value)):
                    raise ValueError('互动指标必须是非负有限数字或 null')
    timestamp(bundle.get('retrieved_at'))
    raw_files = bundle.get('raw_files', [])
    if not isinstance(raw_files, list):
        raise ValueError('raw_files 必须是数组')
    for source in raw_files:
        text(source, 'raw file')
    return bundle


def inspect_raw(path):
    if not path.is_file() or path.suffix.lower() not in ('.json', '.jsonl', '.csv', '.md', '.txt', '.html'):
        raise ValueError('原始文件不存在或格式不支持')
    if re.search(r'cookie|credential|secret|\.env', path.name, re.I):
        raise ValueError('不能归档凭据文件')
    content = path.read_text(encoding='utf-8-sig')
    if path.suffix.lower() == '.json':
        json.loads(content)
    elif path.suffix.lower() == '.jsonl':
        for line in content.splitlines():
            if line.strip():
                json.loads(line)
    elif path.suffix.lower() == '.csv':
        rows = list(csv.reader(io.StringIO(content), strict=True))
        if not rows or not rows[0] or any(len(row) != len(rows[0]) for row in rows[1:] if row):
            raise ValueError('CSV 列数不一致或缺少表头')
    return path


def run_dir(value, writable=True):
    path = Path(value).expanduser().resolve()
    if not (path / 'task.json').is_file() or not (path / 'batches').is_dir():
        raise ValueError('不是任务目录')
    if writable and (path / 'final').exists():
        raise ValueError('任务已定稿；新研究请创建新任务')
    return path


def init(topic, market, days=30, output=None, as_of=None):
    text(topic, 'topic')
    if market not in ('cn', 'global', 'both', 'link', 'product', 'import', 'hot') or not 1 <= days <= 30:
        raise ValueError('market 或 days 无效')
    now = datetime.now(CST)
    end = date.fromisoformat(as_of) if as_of else now.date()
    parent = Path(output).expanduser().resolve() if output else ROOT / 'out'
    parent.mkdir(parents=True, exist_ok=True)
    path = parent / (now.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:10])
    path.mkdir()  # exclusive creation
    (path / 'batches').mkdir()
    dump(path / 'task.json', {'topic': topic, 'market': market, 'created_at': now.isoformat(), 'from_date': (end - timedelta(days=days)).isoformat(), 'to_date': end.isoformat()})
    return path


def ingest(run, bundle_path):
    run = run_dir(run)
    bundle_path = Path(bundle_path).resolve()
    bundle = validate_bundle(json.loads(bundle_path.read_text(encoding='utf-8')))
    sources = [inspect_raw((bundle_path.parent / p).resolve()) for p in bundle.get('raw_files', [])]
    stage = Path(tempfile.mkdtemp(prefix='.batch-', dir=run))
    try:
        raw = stage / 'raw'
        raw.mkdir()
        archives = []
        for i, source in enumerate(sources):
            target = raw / ('%03d-' % i + source.name)
            shutil.copyfile(str(source), str(target))
            archives.append({'file': str(target.relative_to(stage)), 'sha256': hashlib.sha256(target.read_bytes()).hexdigest()})
        saved = dict(bundle)
        saved['raw_files'] = archives
        saved['archived_at'] = datetime.now(CST).isoformat()
        saved['retrieved_at'] = bundle.get('retrieved_at')
        dump(stage / 'bundle.json', saved)
        target = run / 'batches' / uuid.uuid4().hex
        stage.rename(target)
        return target
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def aggregate(run):
    records, runs = {}, []
    for path in sorted((run / 'batches').glob('*/bundle.json')):
        bundle = json.loads(path.read_text(encoding='utf-8'))
        runs.append({'tool': bundle['tool'], 'version': bundle['version'], 'channels': bundle['channels'], 'batch': str(path.parent.relative_to(run)), 'archived_at': bundle['archived_at'], 'retrieved_at': bundle.get('retrieved_at'), 'raw_files': bundle['raw_files']})
        for item in bundle['evidence']:
            # Only identical full URL + platform is merged. Distinct parameterized links survive.
            key = (item['platform'], item['url'])
            if key not in records:
                records[key] = {'id': 'E' + hashlib.sha256(('\0'.join(key)).encode()).hexdigest()[:16], 'url': item['url'], 'platform': item['platform'], 'observations': []}
            records[key]['observations'].append(dict(item, tool=bundle['tool'], version=bundle['version'], batch=str(path.parent.relative_to(run)), archived_at=bundle['archived_at'], retrieved_at=bundle.get('retrieved_at')))
    return {'task': json.loads((run / 'task.json').read_text(encoding='utf-8')), 'runs': runs, 'evidence': list(records.values())}


def finalize(run, brief_path, cards_path=None):
    run = run_dir(run)
    data = aggregate(run)
    brief = Path(brief_path).read_text(encoding='utf-8')
    if not brief.strip():
        raise ValueError('简报不能为空')
    known = {item['id'] for item in data['evidence']}
    refs = set(re.findall(r'\[(E[a-f0-9]{16})\]', brief))
    if not refs <= known:
        raise ValueError('简报引用不存在的证据')
    if known and not refs:
        raise ValueError('有证据时简报至少引用一个 [E…] 编号')
    cards = None
    if cards_path:
        cards = json.loads(Path(cards_path).read_text(encoding='utf-8'))
        if not isinstance(cards, list):
            raise ValueError('信号卡必须是数组')
        for card in cards:
            fields = ['audience', 'context', 'problem', 'workaround', 'supporting', 'opposing', 'to_verify']
            object_keys(card, fields, fields, 'signal card')
            for key in ['audience', 'context', 'problem', 'workaround', 'to_verify']:
                text(card[key], key)
            for key in ['supporting', 'opposing']:
                if not isinstance(card[key], list) or any(not isinstance(x, str) or x not in known for x in card[key]):
                    raise ValueError('信号卡引用不存在的证据')
            if not card['supporting']:
                raise ValueError('信号卡至少需要一条支持证据')
    stage = Path(tempfile.mkdtemp(prefix='.final-', dir=run))
    try:
        dump(stage / 'run.json', {'task': data['task'], 'runs': data['runs']})
        dump(stage / 'evidence.json', data['evidence'])
        # This appendix is engine-owned; the agent writes interpretation above it.
        appendix = ['\n\n## 实际渠道状态（自动附录）\n']
        for source in data['runs']:
            for c in source['channels']:
                appendix.append('- %s / %s：%s；路径 %s；%s' % (source['tool'], c['platform'], c['status'], c['path'], c['reason']))
        appendix.append('\n## 证据索引\n')
        appendix.extend('- [%s] [%s](%s)' % (e['id'], e['platform'], e['url']) for e in data['evidence'])
        (stage / 'report.md').write_text(brief + '\n'.join(appendix) + '\n', encoding='utf-8')
        if cards is not None:
            dump(stage / 'signal-cards.json', cards)
        stage.rename(run / 'final')
        return run / 'final'
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def main():
    parser = argparse.ArgumentParser(description='创建研究目录、归档规范证据、定稿；不采集、不生成结论')
    sub = parser.add_subparsers(dest='action', required=True)
    p = sub.add_parser('init'); p.add_argument('--topic', required=True); p.add_argument('--market', required=True, choices=['cn', 'global', 'both', 'link', 'product', 'import', 'hot']); p.add_argument('--days', type=int, default=30); p.add_argument('--output'); p.add_argument('--as-of', help='研究截止日期 YYYY-MM-DD')
    p = sub.add_parser('ingest'); p.add_argument('--run', required=True); p.add_argument('--bundle', required=True)
    p = sub.add_parser('inspect'); p.add_argument('--run', required=True)
    p = sub.add_parser('finalize'); p.add_argument('--run', required=True); p.add_argument('--brief', required=True); p.add_argument('--cards')
    args = parser.parse_args()
    try:
        if args.action == 'init': result = str(init(args.topic, args.market, args.days, args.output, args.as_of))
        elif args.action == 'ingest': result = str(ingest(args.run, args.bundle))
        elif args.action == 'inspect': result = aggregate(run_dir(args.run, writable=False))
        else: result = str(finalize(args.run, args.brief, args.cards))
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, OSError, KeyError, TypeError, csv.Error):
        parser.exit(2, '输入无效或文件不可用；任务未定稿。请检查证据契约与文件格式。\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
