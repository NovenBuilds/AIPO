"""对照依赖清单里的文件指纹。找不到副本时不猜测版本。"""

import hashlib
import json
from pathlib import Path

from aipo.config import repo_root


def _sha256(path: Path):
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def compare_local(config=None):
    manifest = json.loads((repo_root() / "docs" / "依赖清单.json").read_text(encoding="utf-8"))
    projects = config.projects if config is not None else {}
    rows = []
    for provider in manifest["providers"]:
        name = provider["name"]
        settings = projects.get(name) or {}
        raw_path = settings.get("path") or ("upstream/" + name)
        path = Path(raw_path).expanduser()
        if not path.is_absolute():
            path = (config.root if config is not None else repo_root()) / path
        files = []
        present = path.is_dir()
        for rel, expected in (provider.get("local_reference_sha256") or {}).items():
            target = path / rel
            if target.is_file():
                actual = _sha256(target)
                files.append({"file": rel, "expected": expected, "actual": actual, "match": actual == expected})
            else:
                files.append({"file": rel, "expected": expected, "actual": None, "match": False, "missing": True})
        rows.append({
            "name": name,
            "revision": provider.get("revision"),
            "license": provider.get("license"),
            "path": str(path),
            "present": present,
            "files": files,
            "patches": provider.get("patches") or [],
        })
    return {"providers": rows}


def render_local(report):
    lines = []
    for row in report["providers"]:
        if not row["present"]:
            lines.append("%s：本环境没有本地副本（%s）。" % (row["name"], row["path"]))
            continue
        matched = sum(1 for item in row["files"] if item.get("match"))
        lines.append("%s：找到副本，指纹一致 %s/%s。" % (row["name"], matched, len(row["files"])))
    return "\n".join(lines)
