"""调用旧雷达的 save_run，保持证据编号和批次语义。"""

import importlib.util
import json
import tempfile
from pathlib import Path

from aipo.config import repo_root

_SAVE = None


def save_run():
    global _SAVE
    if _SAVE is None:
        path = repo_root() / "legacy" / "topic-signal-radar" / "scripts" / "save_run.py"
        spec = importlib.util.spec_from_file_location("aipo_save_run", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _SAVE = module
    return _SAVE


def check_env():
    path = repo_root() / "legacy" / "topic-signal-radar" / "scripts" / "check_env.py"
    spec = importlib.util.spec_from_file_location("aipo_check_env", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def init_run(topic, market, output):
    return save_run().init(topic, market, days=30, output=str(output))


def ingest_result(run, source_result):
    module = save_run()
    folder = Path(tempfile.mkdtemp(prefix="aipo-bundle-"))
    raw_path = folder / source_result.raw_name
    payload = source_result.raw
    if not isinstance(payload, str):
        raw_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    else:
        raw_path.write_text(payload, encoding="utf-8")
    bundle = {
        "tool": source_result.tool,
        "version": source_result.version,
        "channels": source_result.channels,
        "evidence": source_result.evidence,
        "raw_files": [source_result.raw_name],
    }
    if source_result.retrieved_at:
        bundle["retrieved_at"] = source_result.retrieved_at
    (folder / "bundle.json").write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return module.ingest(run, folder / "bundle.json")


def aggregate(run):
    return save_run().aggregate(save_run().run_dir(run, writable=False))


def finalize(run, brief, cards=None):
    folder = Path(tempfile.mkdtemp(prefix="aipo-brief-"))
    brief_path = folder / "brief.md"
    brief_path.write_text(brief, encoding="utf-8")
    cards_path = None
    if cards is not None:
        cards_path = folder / "cards.json"
        cards_path.write_text(json.dumps(cards, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return save_run().finalize(run, brief_path, cards_path)
