#!/usr/bin/env python3
"""Read-only capability inventory. No installation, credential copying or search."""
import argparse
import json
from pathlib import Path
import shutil
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
# entry, minimum Python, import checks, commands, config location
CATALOG = {
    'last30days-skill': ('skills/last30days/SKILL.md', (3, 12), [], [], '~/.config/last30days'),
    'last30days-skill-cn': ('SKILL.md', (3, 8), ['playwright.sync_api'], [], '~/.config/last30days-cn'),
    'Agent-Reach': ('agent_reach/skill/SKILL.md', (3, 10), ['agent_reach'], ['agent-reach'], '~/.agent-reach'),
    'MediaCrawler': ('README.md', (3, 11), ['playwright.sync_api', 'typer', 'httpx'], [], None),
    'social-media-copilot': ('README.md', None, [], ['node', 'npm'], None),
    'xiaohongshu-mcp': ('README.md', None, [], [], None),
    'goofish-cli': ('README.md', (3, 11), ['goofish_cli', 'playwright.sync_api'], ['goofish'], '~/.goofish-cli'),
    'ai-goofish-monitor': ('README.md', (3, 10), ['fastapi', 'playwright.sync_api'], [], None),
}


def load_config(path=None):
    path = Path(path) if path else ROOT / 'configs/local.json'
    if not path.exists():
        if path != ROOT / 'configs/local.json':
            raise ValueError('指定配置不存在')
        return {}
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict) or set(data) - {'projects'}:
        raise ValueError('配置只允许 projects，不接收凭据或任意命令')
    if not isinstance(data.get('projects', {}), dict):
        raise ValueError('projects 必须是对象')
    for name, settings in data.get('projects', {}).items():
        if name not in CATALOG or not isinstance(settings, dict):
            raise ValueError('未知项目或配置结构错误')
        if set(settings) - {'path', 'python', 'service_url'}:
            raise ValueError('项目配置只允许 path、python、service_url')
        if any(not isinstance(v, str) or not v for v in settings.values()):
            raise ValueError('配置值必须是非空字符串')
        if 'service_url' in settings:
            service_url(settings['service_url'])
    return data.get('projects', {})


def service_url(value):
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('服务地址必须是无凭据、查询参数或片段的 HTTP(S) 地址')
    return value.rstrip('/')


def resolve_path(value):
    p = Path(value).expanduser()
    return (ROOT / p).resolve() if not p.is_absolute() else p.resolve()


def python_info(executable, modules):
    # Run a fixed probe, never user-supplied code. The chosen interpreter is trusted config.
    code = '''import importlib.util,json,sys
result={}
for name in json.loads(sys.argv[1]):
 try: result[name]=importlib.util.find_spec(name) is not None
 except (ModuleNotFoundError,ImportError,ValueError): result[name]=False
print(json.dumps({'version':list(sys.version_info[:3]),'modules':result}))'''
    try:
        proc = subprocess.run([str(executable), '-c', code, json.dumps(modules)], capture_output=True, text=True, timeout=12)
        return json.loads(proc.stdout) if proc.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None


def choose_python(path, override, minimum, modules):
    if override:
        candidates = [str(resolve_path(override)) if '/' in override or '\\' in override else shutil.which(override)]
    else:
        local = [path / '.venv/bin/python', path / '.venv/Scripts/python.exe']
        # An existing dedicated environment is authoritative; do not hide its failure.
        existing = [str(p) for p in local if p.exists()]
        candidates = existing or [shutil.which(x) for x in ('python3.13', 'python3.12', 'python3.11', 'python3', 'python')]
    for candidate in dict.fromkeys(candidates):
        if not candidate:
            continue
        info = python_info(candidate, modules)
        if info and tuple(info['version'][:2]) >= minimum:
            return {'path': candidate, 'version': '.'.join(map(str, info['version'])), 'modules': info['modules']}
    return None


def source_version(path):
    if (path / '.git').exists():
        try:
            proc = subprocess.run(['git', '-C', str(path), 'rev-parse', 'HEAD'], capture_output=True, text=True, timeout=3)
            if proc.returncode == 0 and re.fullmatch(r'[a-f0-9]{40,64}', proc.stdout.strip()):
                return {'revision': proc.stdout.strip(), 'version': None}
        except (OSError, subprocess.TimeoutExpired):
            pass
    # ZIP copies may declare a release version, but never infer their commit.
    for filename in ('pyproject.toml', 'SKILL.md', 'package.json'):
        candidate = path / filename
        if candidate.is_file():
            try:
                content = candidate.read_text(encoding='utf-8')
                if filename == 'package.json':
                    version = json.loads(content).get('version')
                else:
                    match = re.search(r'^version\s*[:=]\s*["\']([^"\'\n]+)', content, re.M)
                    version = match.group(1) if match else None
                if isinstance(version, str):
                    return {'revision': None, 'version': version}
            except (OSError, ValueError):
                pass
    return {'revision': None, 'version': None}


def get_json(url):
    # Never follow redirects, send cookies or log a remote exception body.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    request = urllib.request.Request(url, headers={'Accept': 'application/json'})
    with urllib.request.build_opener(NoRedirect()).open(request, timeout=4) as response:
        return json.loads(response.read(1024 * 1024).decode('utf-8'))


def probe_xhs(base):
    try:
        health = get_json(service_url(base) + '/health')
        if not isinstance(health, dict) or health.get('success') is not True:
            return {'service': 'error', 'login': 'unknown', 'note': '服务响应不符合小红书接口契约'}
    except urllib.error.HTTPError as exc:
        return {'service': 'reachable', 'login': 'unknown', 'note': 'HTTP %s；认证或接口需进一步检查' % exc.code}
    except (OSError, ValueError):
        return {'service': 'unreachable', 'login': 'unknown', 'note': '服务未连通或响应无法解析'}
    try:
        login = get_json(service_url(base) + '/api/v1/login/status')
        data = login.get('data') if isinstance(login, dict) else None
        logged = data.get('is_logged_in') if isinstance(data, dict) else None
        return {'service': 'reachable', 'login': 'valid' if logged is True else 'missing' if logged is False else 'unknown', 'note': '只检查登录，不代表搜索通过'}
    except (OSError, ValueError):
        return {'service': 'reachable', 'login': 'unknown', 'note': '登录检查未通过；未读取凭据'}


def inspect(projects=None, probe=False, selected=None):
    projects = projects or {}
    records = []
    for name in selected or CATALOG:
        entry, minimum, modules, commands, config = CATALOG[name]
        settings = projects.get(name, {})
        path = resolve_path(settings.get('path', 'upstream/' + name))
        record = {'project': name, 'path': str(path), 'source_exists': path.is_dir(), 'entry_exists': (path / entry).is_file(),
                  'python': None, 'dependencies': 'unknown', 'commands': {c: shutil.which(c) for c in commands},
                  'config_path': str(Path(config).expanduser()) if config else None,
                  'service': 'unknown', 'login': 'unknown', 'request': 'unknown'}
        record.update(source_version(path))
        record['config_exists'] = Path(record['config_path']).exists() if record['config_path'] else None
        if minimum:
            info = choose_python(path, settings.get('python'), minimum, modules)
            record['python'] = info
            record['dependencies'] = 'available' if info and all(info['modules'].values()) else 'missing'
        if name == 'last30days-skill-cn':
            cookie_root = Path('~/.config/last30days-cn/browser_cookies').expanduser()
            record['session_files'] = {p: (cookie_root / (p + '_cookies.json')).is_file() for p in ('weibo', 'xiaohongshu', 'zhihu', 'douyin')}
            record['note'] = '会话文件存在不等于有效；配置目录覆盖项需由上游诊断确认'
        if name == 'xiaohongshu-mcp':
            base = settings.get('service_url', 'http://127.0.0.1:18060')
            record['service_url'] = service_url(base)
            if probe:
                record.update(probe_xhs(base))
        if name == 'social-media-copilot':
            record['note'] = '需由智能体检查宿主工具或插件；不能由源码存在推断已安装'
        records.append(record)
    return {'root': str(ROOT), 'probe': probe, 'projects': records}


def main():
    parser = argparse.ArgumentParser(description='八项上游只读检查；不安装、不登录、不搜索')
    parser.add_argument('--config')
    parser.add_argument('--project', choices=list(CATALOG), action='append')
    parser.add_argument('--probe', action='store_true', help='额外探测小红书服务与登录接口')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    try:
        result = inspect(load_config(args.config), args.probe, args.project)
    except (ValueError, OSError) as exc:
        parser.exit(2, '配置无法读取或不符合格式：%s\n' % type(exc).__name__)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print('项目根目录：' + result['root'])
        for p in result['projects']:
            print('%s：源码=%s 入口=%s 依赖=%s 服务=%s 登录=%s 真实请求=%s' % (p['project'], p['source_exists'], p['entry_exists'], p['dependencies'], p['service'], p['login'], p['request']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
