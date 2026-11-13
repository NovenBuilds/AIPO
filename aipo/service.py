"""任务入口：发起、查看、恢复。同一重试编号只对应一组参数。"""

import hashlib
import json
import re
import threading
import uuid
from datetime import datetime
from pathlib import Path

from aipo.archive import aggregate
from aipo.config import load_config
from aipo.registry import normalize_platforms
from aipo.report import coverage
from aipo.runner import WAIT_STATUS, Runner
from aipo.store import DONE, PHASE_QUEUED, QUEUED, RUNNING, Store, WAITING
from aipo.triggers import intent

REQUEST_RE = re.compile(r"^[A-Za-z0-9._:-]{1,80}$")


class ServiceError(Exception):
    def __init__(self, message, code="invalid"):
        super().__init__(message)
        self.code = code


def params_hash(question, platforms, mode):
    blob = json.dumps({"question": question, "platforms": platforms, "mode": mode}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()


class Service:
    def __init__(self, config=None, autostart=False):
        self.config = config or load_config()
        self.store = Store(self.config.database)
        self.store.recover_running()
        self.autostart = autostart
        self.model_override = None
        self.plan_override = None
        self.select_override = None
        self.stop_after_archived = None
        self._cv = threading.Condition()
        self._stop = False
        self._worker = None
        if autostart:
            self.start_worker()

    def start_worker(self):
        if self._worker and self._worker.is_alive():
            return
        self._stop = False
        self._worker = threading.Thread(target=self._loop, name="aipo-research", daemon=True)
        self._worker.start()

    def close(self):
        self._stop = True
        self._kick()

    def _loop(self):
        while not self._stop:
            research_id = self.store.next_queued()
            if research_id and self.store.claim(research_id):
                Runner(self).execute(research_id)
                continue
            with self._cv:
                self._cv.wait(timeout=0.2)

    def _kick(self):
        with self._cv:
            self._cv.notify_all()

    def start(self, question, request_id=None, platforms=None):
        question = self._question(question)
        names = normalize_platforms(platforms)
        if len(names) > 12:
            raise ServiceError("平台范围最多 12 个。")
        if request_id:
            request_id = str(request_id).strip()
            if not REQUEST_RE.fullmatch(request_id):
                raise ServiceError("request_id 只能包含字母、数字、点、下划线、冒号和短横线。")
        else:
            request_id = None
        digest = params_hash(question, names, self.config.mode)
        if request_id:
            existing = self.store.find_request(request_id)
            if existing:
                return self._reuse(existing, digest)
        research_id = "r%s-%s" % (datetime.now().strftime("%Y%m%d%H%M%S"), uuid.uuid4().hex[:8])
        inserted = self.store.insert_research(research_id, request_id, question, names, digest, self.config.mode, intent(question))
        if inserted and not inserted.get("created"):
            return self._reuse(inserted, digest)
        if self.autostart:
            self._kick()
        return {
            "research_id": research_id,
            "status": QUEUED,
            "phase": PHASE_QUEUED,
            "reused": False,
            "mode": self.config.mode,
            "question": question,
            "platforms": names,
        }

    def _reuse(self, existing, digest):
        if existing.get("params_hash") != digest:
            raise ServiceError("request_id 已用于不同参数。原任务是 %s。" % existing.get("id"), "request_conflict")
        view = self.get(existing["id"])
        view["reused"] = True
        view["note"] = "同一 request_id 与相同参数复用任务，未新建研究。"
        return view

    def run(self, research_id):
        if not self.store.claim(research_id):
            return False
        Runner(self).execute(research_id)
        return True

    def resume(self, research_id, answer=None, sync=False):
        row = self.store.get(research_id)
        if not row:
            raise ServiceError("未找到任务。", "not_found")
        if row["status"] == DONE:
            view = self.get(research_id)
            view["note"] = "任务已完成，未重新取证。"
            view["reused"] = True
            return view
        if row["status"] == RUNNING:
            view = self.get(research_id)
            view["note"] = "任务正在执行，未并行重复启动。"
            return view
        if row["status"] == WAITING and not (answer and str(answer).strip()):
            raise ServiceError("需要补充信息：登录或依赖尚未恢复。", "need_answer")
        if answer and str(answer).strip():
            self.store.update(research_id, answer=str(answer).strip())
        self.store.requeue(research_id)
        self.store.event(research_id, "resume", "按原任务编号继续。")
        if sync:
            self.run(research_id)
            view = self.get(research_id)
            view["resumed"] = True
            return view
        if self.autostart:
            self._kick()
        return {"research_id": research_id, "status": QUEUED, "phase": PHASE_QUEUED, "accepted": True}

    def get(self, research_id):
        row = self.store.get(research_id)
        if not row:
            raise ServiceError("未找到任务。", "not_found")
        sources = []
        for item in self.store.sources(research_id):
            sources.append({
                "ordinal": item["ordinal"],
                "source": item["source"],
                "platforms": json.loads(item["platforms_json"]),
                "capabilities": json.loads(item["capabilities_json"]),
                "status": item["status"],
                "reason": item["reason"],
                "path": item["path"],
                "mode": item["mode"],
                "version": item["version"],
                "read_depth": item["read_depth"],
                "batch_path": item["batch_path"],
                "attempts": item["attempts"],
            })
        evidence = []
        report = None
        finalized = False
        archive = row.get("archive_path")
        if archive:
            root = Path(archive)
            final_report = root / "final" / "report.md"
            draft_report = root / "draft" / "report.md"
            if final_report.is_file():
                report = final_report.read_text(encoding="utf-8")
                finalized = True
            elif draft_report.is_file():
                report = draft_report.read_text(encoding="utf-8")
            if (root / "task.json").is_file() and (root / "batches").is_dir():
                evidence = aggregate(root).get("evidence") or []
        plan_data = json.loads(row["plan_json"]) if row.get("plan_json") else None
        return {
            "research_id": row["id"],
            "status": row["status"],
            "phase": row["phase"],
            "question": row["question"],
            "mode": row["mode"],
            "intent": row.get("intent"),
            "platforms": json.loads(row["platforms_json"]),
            "plan": plan_data,
            "archive_path": archive,
            "sources": sources,
            "coverage": coverage(sources, {"evidence": evidence}),
            "evidence_index": [
                {"id": item["id"], "platform": item["platform"], "url": item["url"],
                 "access": (item.get("observations") or [{}])[-1].get("access")}
                for item in evidence
            ],
            "report_markdown": report,
            "finalized": finalized,
            "blockers": [item for item in sources if item["status"] in WAIT_STATUS],
            "events": self.store.events(row["id"]),
            "error": row.get("error"),
        }

    def _question(self, question):
        if not isinstance(question, str) or not question.strip():
            raise ServiceError("question 必须是非空的一句话。")
        question = question.strip()
        if len(question) > 2000:
            raise ServiceError("question 过长。")
        return question
