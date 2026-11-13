"""执行研究：按来源取证、归档、校验引用后定稿。"""

import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from aipo import archive, live, model, replay
from aipo.contract import result
from aipo.planner import clamp_ids, clamp_plan, plan
from aipo.report import build_brief, splice_model_report
from aipo.store import DONE, FAILED, PHASE_DONE, PHASE_FAIL, PHASE_WAIT, RUNNING, WAITING, now

RETRYABLE = {"need_login", "missing_dependency", "error", "timeout", "blocked", "unknown"}
WAIT_STATUS = {"need_login", "missing_dependency", "error"}
SKIP_WORDS = ("跳过", "定稿", "按已有", "不用重试")


def _combined_status(source_result):
    statuses = [channel["status"] for channel in source_result.channels] or ["error"]
    if len(set(statuses)) == 1:
        return statuses[0]
    if "success" in statuses:
        return "degraded"
    return statuses[0]


def _reason(source_result):
    return " ".join(channel["reason"] for channel in source_result.channels if channel.get("reason"))


class Runner:
    def __init__(self, service):
        self.service = service

    def execute(self, research_id):
        try:
            self._execute(research_id)
        except Exception as exc:
            message = "%s：%s" % (type(exc).__name__, exc)
            self.service.store.update(research_id, status=FAILED, phase=PHASE_FAIL, error=message[:500])
            self.service.store.event(research_id, "failed", message[:500])

    def _execute(self, research_id):
        self._research_id = research_id
        store = self.service.store
        config = self.service.config
        row = store.get(research_id)
        already_planned = bool(row.get("plan_json"))
        planned = json.loads(row["plan_json"]) if already_planned else plan(row["question"], json.loads(row["platforms_json"]))
        if not already_planned:
            planned = self._refine_plan(research_id, row["question"], planned)
            store.update(research_id, plan_json=json.dumps(planned, ensure_ascii=False), intent=planned["intent"])
        run = Path(row["archive_path"]) if row.get("archive_path") else archive.init_run(row["question"], planned["market"], config.archive_root)
        if not row.get("archive_path"):
            store.update(research_id, archive_path=str(run))
        if (run / "final").is_dir():
            store.update(research_id, status=DONE, phase=PHASE_DONE, error=None)
            store.event(research_id, "finalized", "归档已经定稿，未重复取证。")
            return
        store.ensure_sources(research_id, planned["jobs"])
        answer = row.get("answer") or ""
        skip = any(word in answer for word in SKIP_WORDS)
        todo = []
        for source in store.sources(research_id):
            if source["status"] == "pending" or (answer and not skip and source["status"] in RETRYABLE):
                todo.append(source)
        fetched = self._fetch_all(todo, planned, row["question"])
        for index, source in enumerate(todo, start=1):
            source_result = fetched[source["ordinal"]]
            status = _combined_status(source_result)
            batch_path = ""
            try:
                batch = archive.ingest_result(run, source_result)
                batch_path = str(Path(batch).relative_to(run))
            except (ValueError, OSError) as exc:
                status = "error"
                source_result.channels.append({
                    "platform": source["platforms_json"], "status": "error", "path": "archive", "reason": "归档失败：%s" % type(exc).__name__,
                })
            store.save_source(
                research_id, source["ordinal"], status=status, reason=_reason(source_result)[:500],
                path=source_result.channels[0]["path"] if source_result.channels else "",
                mode=source_result.mode, version=source_result.version, read_depth=source_result.read_depth,
                batch_path=batch_path, attempts=source["attempts"] + 1, started_at=now(),
            )
            store.event(research_id, "source", "%s 完成，状态 %s。" % (source["source"], status))
            stop_after = getattr(self.service, "stop_after_archived", None)
            if stop_after is not None and index >= stop_after:
                store.update(research_id, status=RUNNING, phase="取证")
                store.event(research_id, "stopped", "按检查点停住，尚未定稿。")
                return
        sources = self._public_sources(research_id)
        data = archive.aggregate(run)
        extra = self._model_note(research_id, row["question"], data)
        brief, cards = build_brief(row["question"], data, sources, planned, config.mode)
        spliced = splice_model_report(brief, extra) if extra else None
        if spliced:
            brief = spliced
            store.event(research_id, "model_report", "模型判断已通过引用检查并写入报告。")
        elif extra:
            brief = brief.rstrip() + "\n\n## 模型补充\n\n" + extra + "\n"
            store.event(research_id, "model", "模型补充已通过引用检查。")
        blocked = [item for item in sources if item["status"] in WAIT_STATUS]
        if blocked and not skip:
            draft = run / "draft"
            draft.mkdir(exist_ok=True)
            (draft / "report.md").write_text(brief, encoding="utf-8")
            store.update(research_id, status=WAITING, phase=PHASE_WAIT, error=None)
            store.event(research_id, "waiting", "有来源需要登录、配置或连通后再继续。已完成批次已保留。")
            return
        archive.finalize(run, brief, cards)
        store.update(research_id, status=DONE, phase=PHASE_DONE, error=None)
        store.event(research_id, "finalized", "报告已定稿。")

    def _fetch_all(self, todo, planned, question):
        if not todo:
            return {}
        jobs = {job["ordinal"]: job for job in planned["jobs"]}
        timeout = self.service.config.source_timeout_seconds + 2
        output = {}
        selector = self._selector(question)

        def fetch(source):
            job = jobs[source["ordinal"]]
            attempt = source["attempts"] + 1
            if self.service.config.mode == "replay":
                return replay.collect(job, planned["kind"], attempt)
            return live.collect(job, self.service.config, attempt, planned["kind"], select=selector)

        def guarded(source):
            box = {}

            def target():
                try:
                    box["value"] = fetch(source)
                except Exception as exc:
                    box["error"] = exc

            thread = threading.Thread(target=target, daemon=True)
            thread.start()
            thread.join(timeout)
            if thread.is_alive():
                tool = source["source"] if source["source"] != "unregistered" else "host-web"
                return result(tool, self.service.config.mode, "timeout", "来源", "timeout", "来源超过限定时间。", registration="受阻")
            if "error" in box:
                tool = source["source"] if source["source"] != "unregistered" else "host-web"
                return result(tool, self.service.config.mode, "error", "来源", "error", "来源执行失败：%s。" % type(box["error"]).__name__, registration="受阻")
            return box["value"]

        with ThreadPoolExecutor(max_workers=min(4, len(todo))) as pool:
            futures = {pool.submit(guarded, source): source["ordinal"] for source in todo}
            for future in as_completed(futures):
                output[futures[future]] = future.result()
        return output

    def _public_sources(self, research_id):
        rows = []
        for row in self.service.store.sources(research_id):
            item = dict(row)
            item["platforms"] = json.loads(row["platforms_json"])
            item["capabilities"] = json.loads(row["capabilities_json"])
            rows.append(item)
        return rows

    def _refine_plan(self, research_id, question, planned):
        override = self.service.plan_override
        if override is None and not self.service.config.model_enabled():
            return planned
        try:
            proposal = override(question, planned) if override is not None else model.propose_plan(self.service.config, question, planned)
        except (OSError, ValueError, TypeError):
            proposal = None
        refined = clamp_plan(question, planned, proposal)
        if refined is None:
            self.service.store.event(research_id, "model_plan_rejected", "模型计划未通过约束，已沿用程序计划。")
            return planned
        self.service.store.event(research_id, "model_plan", "模型关键词：%s。" % "、".join(refined["keywords"]))
        return refined

    def _selector(self, question):
        def select(cards, limit):
            override = self.service.select_override
            if override is None and not self.service.config.model_enabled():
                return None
            try:
                proposal = override(question, cards, limit) if override is not None else model.propose_selection(
                    self.service.config, question, cards, limit)
            except (OSError, ValueError, TypeError):
                proposal = None
            chosen = clamp_ids(cards, limit, proposal)
            if not chosen:
                self.service.store.event(self._research_id, "model_select_rejected", "模型没有给出可用的深读编号，已按预算默认深读。")
                return None
            self.service.store.event(self._research_id, "model_select", "深读：%s。" % "、".join(chosen))
            return chosen

        return select

    def _model_note(self, research_id, question, aggregate):
        config = self.service.config
        override = self.service.model_override
        if not config.model_enabled() and override is None:
            return None
        ids = []
        lines = []
        allowed_numbers = set(numbers_in(question))
        for item in aggregate.get("evidence") or []:
            ids.append(item["id"])
            observation = item["observations"][0] if item.get("observations") else {}
            title = observation.get("title") or item["url"]
            summary = observation.get("summary") or ""
            lines.append("[%s] %s %s" % (item["id"], title, summary[:240]))
            allowed_numbers.update(numbers_in(item["id"]))
            allowed_numbers.update(numbers_in(title))
            allowed_numbers.update(numbers_in(summary))
        if not ids:
            self.service.store.event(research_id, "model_skipped", "没有证据编号，未采用模型草稿。")
            return None
        try:
            if override is not None:
                text = override(question, ids, lines)
            elif config.model_enabled():
                text = model.propose_report(config, question, ids, lines)
            else:
                text = None
        except (OSError, ValueError, TypeError):
            text = None
        cited = set(re_ids(text or ""))
        numbers = set(numbers_in(text or ""))
        if not text or not cited or not cited <= set(ids) or not numbers <= allowed_numbers or "实采成功" in text or "登记：实采" in text or "登记：" in text:
            self.service.store.event(research_id, "model_rejected", "模型草稿未通过引用校验，已改用程序简报。")
            return None
        return text.strip()


def re_ids(text):
    import re
    return re.findall(r"\[(E[a-f0-9]{16})\]", text or "")


def numbers_in(text):
    import re
    return re.findall(r"\d+(?:\.\d+)?", text or "")
