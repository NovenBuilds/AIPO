"""读取服务配置。密钥只允许从环境变量进入进程，不能写进配置文件。"""

import json
import os
from pathlib import Path

MODES = {"replay", "live", "auto"}
SECRET_KEYS = {"token", "cookie", "cookies", "password", "secret", "api_key", "authorization", "session"}


def repo_root():
    env = os.environ.get("AIPO_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    return Path(__file__).resolve().parents[1]


class ConfigError(ValueError):
    pass


class Config:
    def __init__(self, data, path, root):
        self.data = data
        self.path = path
        self.root = root
        mode = os.environ.get("AIPO_MODE") or data.get("mode") or "replay"
        if mode not in MODES:
            raise ConfigError("mode 只能是 replay、live 或 auto")
        # auto 与 live 一样不会用回放夹具填补失败。
        self.mode = "live" if mode == "auto" else mode
        self.requested_mode = mode
        self.database = self._resolve(data.get("database") or "data/aipo.sqlite")
        self.archive_root = self._resolve(data.get("archive_root") or "runs")
        timeout = data.get("source_timeout_seconds", 25)
        if isinstance(timeout, bool) or not isinstance(timeout, int) or not 1 <= timeout <= 300:
            raise ConfigError("source_timeout_seconds 必须是 1 到 300 的整数")
        self.source_timeout_seconds = timeout
        self.projects = data.get("projects") or {}
        self.imports = data.get("imports") or {}
        model = data.get("model") or {}
        self.model_base_url = os.environ.get("AIPO_MODEL_BASE_URL") or model.get("base_url") or ""
        self.model_name = os.environ.get("AIPO_MODEL_NAME") or model.get("name") or ""
        self.model_api_key_env = model.get("api_key_env") or "AIPO_MODEL_API_KEY"
        self.model_timeout = int(model.get("timeout_seconds") or 45)
        if self.model_base_url and not str(self.model_base_url).startswith(("http://", "https://")):
            raise ConfigError("模型地址必须是 HTTP(S)")

    def _resolve(self, value):
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = self.root / path
        return path.resolve()

    def project(self, name):
        settings = self.projects.get(name) or {}
        if not isinstance(settings, dict):
            raise ConfigError("项目配置必须是对象")
        return settings

    def project_path(self, name, default):
        settings = self.project(name)
        value = settings.get("path") or default
        return self._resolve(value)

    def service_url(self, name, default):
        value = self.project(name).get("service_url") or default
        return str(value).rstrip("/")

    def import_path(self, name):
        value = self.imports.get(name)
        if not value:
            return None
        return self._resolve(value)

    def model_api_key(self):
        return os.environ.get(self.model_api_key_env) or ""

    def model_enabled(self):
        return bool(self.model_base_url and self.model_name and self.model_api_key())

    def check_env_projects(self):
        """只把归档诊断允许的字段交给 check_env。"""
        projects = {}
        for name, settings in self.projects.items():
            if not isinstance(settings, dict):
                continue
            picked = {}
            for key in ("path", "python", "service_url"):
                if key in settings and settings[key]:
                    value = settings[key]
                    if key == "path":
                        value = str(self._resolve(value))
                    picked[key] = value
            if picked:
                projects[name] = picked
        return projects


def _reject_secrets(value, where):
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in SECRET_KEYS:
                raise ConfigError("配置不能包含凭据字段：%s" % key)
            _reject_secrets(item, where)
    elif isinstance(value, list):
        for item in value:
            _reject_secrets(item, where)


def load_config(path=None):
    root = repo_root()
    if path is None:
        path = os.environ.get("AIPO_CONFIG")
    if path:
        file = Path(path).expanduser()
        if not file.is_absolute():
            file = (Path.cwd() / file).resolve()
        if not file.is_file():
            raise ConfigError("指定配置不存在")
    else:
        local = root / "configs" / "aipo.local.json"
        example = root / "configs" / "aipo.example.json"
        file = local if local.is_file() else example
        if not file.is_file():
            raise ConfigError("找不到配置")
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError("配置不是合法 JSON") from exc
    if not isinstance(data, dict):
        raise ConfigError("配置必须是对象")
    allowed = {"mode", "database", "archive_root", "source_timeout_seconds", "projects", "imports", "model"}
    extra = set(data) - allowed
    if extra:
        raise ConfigError("配置含未知字段")
    _reject_secrets(data, file)
    projects = data.get("projects") or {}
    imports = data.get("imports") or {}
    model = data.get("model") or {}
    if not isinstance(projects, dict) or not isinstance(imports, dict) or not isinstance(model, dict):
        raise ConfigError("projects、imports、model 必须是对象")
    for name, settings in projects.items():
        if not isinstance(settings, dict):
            raise ConfigError("项目配置必须是对象")
        allowed_project = {"path", "python", "service_url", "allow_noncommercial_learning"}
        if set(settings) - allowed_project:
            raise ConfigError("项目配置只允许路径、解释器、服务地址和非商业许可开关")
        if "allow_noncommercial_learning" in settings and not isinstance(settings["allow_noncommercial_learning"], bool):
            raise ConfigError("allow_noncommercial_learning 必须是布尔值")
    if set(model) - {"base_url", "name", "api_key_env", "timeout_seconds"}:
        raise ConfigError("模型配置只允许地址、名称、密钥环境变量名和超时")
    return Config(data, file, root)
