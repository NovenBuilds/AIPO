import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from aipo.config import ConfigError, load_config, repo_root
from aipo.fingerprints import compare_local
from aipo.mcp_server import read_message, write_message
from aipo.registry import SOURCES, render_matrix_md
from aipo.service import Service, ServiceError

QUESTION = "我会开发微信小程序，每周能投入 5 小时，帮我找一个值得试着收钱的方向，优先看小红书和闲鱼"
ROOT = repo_root()


class ServiceCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.service = self.make()

    def tearDown(self):
        self.service.close()
        self.tmp.cleanup()

    def make(self, mode="replay", **extra):
        data = {
            "mode": mode,
            "database": str(self.root / "aipo.sqlite"),
            "archive_root": str(self.root / "runs"),
            "source_timeout_seconds": 3,
            "projects": {
                "xiaohongshu-mcp": {"path": str(self.root / "no-xhs"), "service_url": "http://127.0.0.1:9"},
                "goofish-cli": {"path": str(self.root / "no-goofish")},
                "last30days-skill": {"path": str(self.root / "no-global")},
                "last30days-skill-cn": {"path": str(self.root / "no-cn")},
                "Agent-Reach": {"path": str(self.root / "no-reach")},
                "MediaCrawler": {"path": str(self.root / "no-crawler"), "allow_noncommercial_learning": False},
                "social-media-copilot": {"path": str(self.root / "no-copilot")},
                "ai-goofish-monitor": {"path": str(self.root / "no-monitor")},
            },
            "imports": {},
        }
        data.update(extra)
        path = self.root / ("config-%s.json" % mode)
        path.write_text(json.dumps(data), encoding="utf-8")
        os.environ.pop("AIPO_MODE", None)
        os.environ.pop("AIPO_CONFIG", None)
        return Service(load_config(path), autostart=False)

    def finish(self, question, platforms=None, request_id=None, service=None):
        service = service or self.service
        snap = service.start(question, request_id, platforms)
        self.assertEqual(snap["status"], "等待")
        self.assertFalse(snap["reused"])
        service.run(snap["research_id"])
        return service.get(snap["research_id"])

    def test_miniprogram_replay_report(self):
        view = self.finish(QUESTION)
        self.assertEqual(view["status"], "已完成")
        self.assertEqual(view["intent"], "找新项目")
        self.assertEqual(view["coverage"]["registration"], "回放")
        self.assertEqual(view["coverage"]["live_success_count"], 0)
        report = view["report_markdown"]
        for phrase in ("目标客户", "反例", "挂牌", "成交", "最小付费验证", "停止条件", "结论缺口", "讨论", "评论", "供给", "获客", "登记：回放。本任务没有实采结果。"):
            self.assertIn(phrase, report)
        self.assertIn("门店手工汇总太耗时", report)
        self.assertIn("表格公式", report)
        self.assertIn("9.9", report)
        self.assertNotIn("登记：实采", report)
        sources = {item["source"]: item for item in view["sources"]}
        self.assertEqual(set(sources), {"xiaohongshu-mcp", "goofish-cli"})
        self.assertEqual(sources["xiaohongshu-mcp"]["mode"], "replay")
        self.assertEqual(sources["xiaohongshu-mcp"]["status"], "success")
        self.assertIn("评论", sources["xiaohongshu-mcp"]["read_depth"])
        self.assertEqual(sources["goofish-cli"]["status"], "success")
        self.assertIsNone(sources["goofish-cli"]["version"])
        evidence = json.loads((Path(view["archive_path"]) / "final" / "evidence.json").read_text(encoding="utf-8"))
        ids = {item["id"] for item in evidence}
        self.assertGreaterEqual(len(ids), 4)
        for item in evidence:
            self.assertIn("[%s]" % item["id"], report)
            self.assertTrue(item["id"].startswith("E"))
            url = item["url"]
            digest = hashlib.sha256(("\0".join((item["platform"], url))).encode()).hexdigest()[:16]
            self.assertEqual(item["id"], "E" + digest)
        self.assertTrue((Path(view["archive_path"]) / "final" / "signal-cards.json").is_file())
        self.assertIn("实际渠道状态", report)
        self.assertIn("docs/回放样例.json", sources["xiaohongshu-mcp"]["reason"])

    def test_duplicate_and_conflict(self):
        first = self.service.start(QUESTION, "retry-1")
        self.service.run(first["research_id"])
        second = self.service.start(QUESTION, "retry-1")
        self.assertTrue(second["reused"])
        self.assertEqual(second["research_id"], first["research_id"])
        self.assertEqual(second["status"], "已完成")
        with self.assertRaises(ServiceError) as caught:
            self.service.start("另一句完全不同的问题", "retry-1")
        self.assertEqual(caught.exception.code, "request_conflict")
        self.assertIn(first["research_id"], str(caught.exception))

    def test_session_resume_reuses_batch(self):
        view = self.finish("会话失效：优先看小红书和闲鱼")
        self.assertEqual(view["status"], "等待用户")
        self.assertTrue(view["blockers"])
        self.assertIn("会话", view["report_markdown"])
        goofish = next(item for item in view["sources"] if item["source"] == "goofish-cli")
        self.assertEqual(goofish["status"], "success")
        self.assertEqual(goofish["attempts"], 1)
        with self.assertRaises(ServiceError):
            self.service.resume(view["research_id"])
        done = self.service.resume(view["research_id"], "已重新登录", sync=True)
        self.assertEqual(done["status"], "已完成")
        self.assertIn("门店手工汇总太耗时", done["report_markdown"])
        self.assertIn("9.9", done["report_markdown"])
        self.assertIn("不是用户重新登录后的实采", done["report_markdown"])
        again = next(item for item in done["sources"] if item["source"] == "goofish-cli")
        self.assertEqual(again["attempts"], 1)
        xhs = next(item for item in done["sources"] if item["source"] == "xiaohongshu-mcp")
        self.assertEqual(xhs["attempts"], 2)
        self.assertEqual(xhs["status"], "success")
        batches = list((Path(done["archive_path"]) / "batches").iterdir())
        self.assertEqual(len(batches), 3)

    def test_timeout_empty_insufficient_and_unknown(self):
        timed = self.finish("部分来源超时：优先看小红书和闲鱼")
        self.assertEqual(timed["status"], "已完成")
        self.assertTrue(any(item["status"] == "timeout" and item["source"] == "goofish-cli" for item in timed["sources"]))
        self.assertIn("超时", timed["report_markdown"])
        self.assertIn("门店手工汇总太耗时", timed["report_markdown"])
        self.assertNotIn("9.9", timed["report_markdown"])
        empty = self.finish("空结果：这个方向近期没有讨论")
        self.assertEqual(empty["status"], "已完成")
        self.assertTrue(any(item["status"] == "empty" for item in empty["sources"]))
        self.assertIn("空结果", empty["report_markdown"])
        self.assertIn("证据不足", empty["report_markdown"])
        self.assertFalse((Path(empty["archive_path"]) / "final" / "signal-cards.json").exists())
        thin = self.finish("证据不足：只有一条公开摘要")
        self.assertEqual(thin["status"], "已完成")
        self.assertIn("证据不足", thin["report_markdown"])
        self.assertIn("现在不要开发", thin["report_markdown"])
        unknown = self.finish("指定平台看看某未知集市", ["某未知集市"])
        self.assertEqual(unknown["status"], "已完成")
        self.assertTrue(any(item["status"] == "blocked" for item in unknown["sources"]))
        self.assertIn("未登记", unknown["report_markdown"])

    def test_compare_specified_public_read_import_catalog(self):
        compared = self.finish("国内外对照：有没有人愿意为表格自动化付费")
        self.assertEqual(compared["coverage"]["registration"], "回放")
        self.assertTrue(compared["coverage"]["public_index_ids"])
        self.assertTrue(compared["coverage"]["in_site_ids"])
        self.assertIn("公开索引", compared["report_markdown"])
        self.assertIn("站内", compared["report_markdown"])
        names = {item["source"] for item in compared["sources"]}
        self.assertEqual(names, {"last30days-skill-cn", "last30days-skill"})
        specified = self.finish("指定平台只看 B站 的表格讨论")
        self.assertEqual({item["source"] for item in specified["sources"]}, {"last30days-skill-cn"})
        platforms = {row["platform"] for row in specified["evidence_index"]}
        self.assertEqual(platforms, {"B站"})
        public = self.finish("指定小红书不可用时补充公开线索")
        self.assertEqual(public["status"], "等待用户")
        skipped = self.service.resume(public["research_id"], "跳过并按已有证据定稿", sync=True)
        self.assertEqual(skipped["status"], "已完成")
        self.assertIn("公开线索", skipped["report_markdown"])
        self.assertIn("不能代替站内", skipped["report_markdown"])
        self.assertTrue(any(item["status"] == "need_login" and item["source"] == "xiaohongshu-mcp" for item in skipped["sources"]))
        read = self.finish("补读 https://example.invalid/docs/pricing 里的收费说明")
        self.assertEqual({item["source"] for item in read["sources"]}, {"Agent-Reach"})
        self.assertIn("https://example.invalid/docs/pricing", read["report_markdown"])
        self.assertIn("未请求该网址", read["report_markdown"])
        imported = self.finish("导入已有评论、插件导出和闲鱼监控")
        self.assertEqual({item["source"] for item in imported["sources"]}, {"MediaCrawler", "social-media-copilot", "ai-goofish-monitor"})
        self.assertIn("没有启动爬虫", imported["report_markdown"])
        self.assertIn("合成夹具", imported["report_markdown"])
        self.assertEqual(imported["coverage"]["registration"], "回放")
        catalog = self.finish("全来源回放：微信小程序收费方向，覆盖小红书、闲鱼、国内外检索、补读、评论和导入")
        self.assertEqual({item["source"] for item in catalog["sources"]}, {item["id"] for item in SOURCES})
        self.assertTrue(all(item["status"] != "pending" for item in catalog["sources"]))
        self.assertTrue(all(item["mode"] == "replay" for item in catalog["sources"]))
        self.assertEqual(catalog["coverage"]["registration"], "回放")
        self.assertEqual(catalog["coverage"]["live_success_count"], 0)

    def test_restart_keeps_finished_batch(self):
        self.service.stop_after_archived = 1
        snap = self.service.start(QUESTION)
        self.service.run(snap["research_id"])
        stopped = self.service.get(snap["research_id"])
        self.assertEqual(stopped["status"], "执行中")
        self.assertEqual(len(list((Path(stopped["archive_path"]) / "batches").iterdir())), 1)
        resumed = Service(self.service.config, autostart=False)
        try:
            row = resumed.store.get(snap["research_id"])
            self.assertEqual(row["status"], "等待")
            self.assertEqual(row["phase"], "中断待恢复")
            done = resumed.resume(snap["research_id"], sync=True)
        finally:
            resumed.close()
        self.assertEqual(done["status"], "已完成")
        self.assertEqual(done["research_id"], snap["research_id"])
        self.assertIn("门店手工汇总太耗时", done["report_markdown"])
        self.assertIn("9.9", done["report_markdown"])
        attempts = {item["source"]: item["attempts"] for item in done["sources"]}
        self.assertEqual(attempts["xiaohongshu-mcp"], 1)
        self.assertEqual(attempts["goofish-cli"], 1)

    def test_live_mode_does_not_replay_sample(self):
        live = self.make("live")
        try:
            snap = live.start(QUESTION)
            live.run(snap["research_id"])
            view = live.get(snap["research_id"])
        finally:
            live.close()
        self.assertEqual(view["status"], "等待用户")
        self.assertEqual(view["coverage"]["registration"], "受阻")
        self.assertEqual(view["coverage"]["live_success_count"], 0)
        self.assertNotIn("门店手工汇总", view["report_markdown"])
        self.assertIn("本任务没有实采结果。", view["report_markdown"])
        self.assertNotIn("登记：实采", view["report_markdown"])
        self.assertTrue(any(item["status"] in ("error", "missing_dependency") for item in view["sources"]))

    def test_live_import_is_not_collection(self):
        fixture = ROOT / "aipo" / "fixtures"
        live = self.make("live", imports={
            "MediaCrawler": str(fixture / "mediacrawler-comments.jsonl"),
            "social-media-copilot": str(fixture / "copilot-export.json"),
            "ai-goofish-monitor": str(fixture / "goofish-monitor.csv"),
        })
        try:
            snap = live.start("导入已有评论、插件导出和闲鱼监控")
            live.run(snap["research_id"])
            view = live.get(snap["research_id"])
        finally:
            live.close()
        self.assertEqual(view["status"], "已完成")
        self.assertEqual(view["coverage"]["registration"], "导入")
        self.assertEqual(view["coverage"]["live_success_count"], 0)
        self.assertIn("登记：导入。本任务没有实采结果。", view["report_markdown"])
        self.assertIn("合成夹具", view["report_markdown"])
        self.assertTrue(all(item["mode"] == "import" for item in view["sources"]))

    def test_bad_citation_does_not_finalize(self):
        import aipo.runner as runner
        original = runner.build_brief
        runner.build_brief = lambda *args, **kwargs: ("见 [E0000000000000000]。\n", None)
        try:
            view = self.finish(QUESTION)
        finally:
            runner.build_brief = original
        self.assertEqual(view["status"], "失败")
        self.assertFalse((Path(view["archive_path"]) / "final").exists())

    def test_model_draft_must_cite(self):
        self.service.model_override = lambda question, ids, lines: "模型没有给编号。"
        rejected = self.finish(QUESTION)
        self.assertEqual(rejected["status"], "已完成")
        self.assertTrue(any(item["kind"] == "model_rejected" for item in rejected["events"]))
        self.assertNotIn("模型没有给编号", rejected["report_markdown"])
        self.assertNotIn("模型补充", rejected["report_markdown"])

        def accepted(question, ids, lines):
            return "模型只复述已有编号 [%s]。" % ids[0]

        self.service.model_override = accepted
        other = self.finish(QUESTION + " 再看一版")
        self.assertIn("模型补充", other["report_markdown"])
        self.assertIn(other["evidence_index"][0]["id"], other["report_markdown"])

    def test_resume_completed_is_stable(self):
        view = self.finish(QUESTION)
        before = sorted(path.name for path in (Path(view["archive_path"]) / "batches").iterdir())
        again = self.service.resume(view["research_id"], "请重试", sync=True)
        after = sorted(path.name for path in (Path(view["archive_path"]) / "batches").iterdir())
        self.assertEqual(before, after)
        self.assertIn("未重新取证", again["note"])

    def test_running_resume_does_not_duplicate(self):
        self.service.store.insert_research("r-manual", None, QUESTION, [], "hash", "replay", "找新项目")
        self.service.store.update("r-manual", status="执行中", phase="取证")
        view = self.service.resume("r-manual")
        self.assertIn("正在执行", view["note"])


class ProtocolTests(unittest.TestCase):
    def test_lsp_and_ndjson_framing(self):
        import io
        payload = {"jsonrpc": "2.0", "id": 1, "method": "ping"}
        buffer = io.BytesIO()
        write_message(buffer, payload, "ndjson")
        buffer.seek(0)
        message, framing = read_message(buffer)
        self.assertEqual(framing, "ndjson")
        self.assertEqual(message["method"], "ping")
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        framed = io.BytesIO(b"Content-Length: %d\r\n\r\n" % len(raw) + raw)
        message, framing = read_message(framed)
        self.assertEqual(framing, "lsp")
        self.assertEqual(message["id"], 1)

    def test_mcp_roundtrip(self):
        folder = tempfile.TemporaryDirectory()
        try:
            root = Path(folder.name)
            config = {
                "mode": "replay",
                "database": str(root / "aipo.sqlite"),
                "archive_root": str(root / "runs"),
                "source_timeout_seconds": 5,
                "projects": {},
            }
            path = root / "config.json"
            path.write_text(json.dumps(config), encoding="utf-8")
            env = os.environ.copy()
            env["AIPO_CONFIG"] = str(path)
            env["PYTHONPATH"] = str(ROOT)
            env["PYTHONUNBUFFERED"] = "1"
            env.pop("AIPO_MODE", None)
            proc = subprocess.Popen(
                [os.environ.get("PYTHON", "python3"), "-m", "aipo", "serve"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, cwd=str(ROOT),
            )
            import select
            import threading
            stderr_chunks = []

            def drain():
                while True:
                    chunk = proc.stderr.readline()
                    if not chunk:
                        break
                    stderr_chunks.append(chunk)

            threading.Thread(target=drain, daemon=True).start()

            def send(message):
                proc.stdin.write((json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8"))
                proc.stdin.flush()

            def read():
                ready, _, _ = select.select([proc.stdout], [], [], 8)
                self.assertTrue(ready, b"".join(stderr_chunks)[-2000:])
                line = proc.stdout.readline()
                self.assertTrue(line)
                return json.loads(line.decode("utf-8"))
            send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "test", "version": "0"}}})
            init = read()
            self.assertEqual(init["result"]["serverInfo"]["name"], "aipo")
            send({"jsonrpc": "2.0", "method": "notifications/initialized"})
            send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
            tools = read()["result"]["tools"]
            self.assertEqual([item["name"] for item in tools], ["start_research", "get_research", "resume_research"])
            send({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "start_research", "arguments": {"question": QUESTION, "request_id": "mcp-1"}}})
            started = read()["result"]["content"][0]["text"]
            self.assertIn("等待", started)
            marker = started.rfind("```json")
            meta = json.loads(started[marker + 7:started.rfind("```")])
            research_id = meta["research_id"]
            seen = ""
            for _ in range(50):
                send({"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "get_research", "arguments": {"research_id": research_id}}})
                seen = read()["result"]["content"][0]["text"]
                if "已完成" in seen and "门店手工汇总太耗时" in seen:
                    break
            self.assertIn("已完成", seen)
            self.assertIn("门店手工汇总太耗时", seen)
            self.assertIn("本任务没有实采结果", seen)
            proc.stdin.close()
            proc.wait(timeout=5)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=5)
            proc.stdout.close()
            proc.stderr.close()
            folder.cleanup()


class InventoryTests(unittest.TestCase):
    def test_matrix_is_documented(self):
        text = (ROOT / "docs" / "平台能力对应.md").read_text(encoding="utf-8")
        self.assertIn(render_matrix_md(), text)
        for source in SOURCES:
            self.assertIn(source["id"], text)

    def test_fingerprint_mismatch_is_explicit(self):
        report = compare_local(load_config(ROOT / "configs" / "aipo.example.json"))
        self.assertTrue(all(not row["present"] for row in report["providers"]))
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            target = root / "go.mod"
            target.write_text("module example\n", encoding="utf-8")
            from aipo.config import Config
            config = load_config(ROOT / "configs" / "aipo.example.json")
            config.projects = {"xiaohongshu-mcp": {"path": str(root)}}
            report = compare_local(config)
            row = next(item for item in report["providers"] if item["name"] == "xiaohongshu-mcp")
            self.assertTrue(row["present"])
            self.assertFalse(row["files"][0]["match"])

    def test_config_rejects_secrets(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "local.json"
            path.write_text(json.dumps({"projects": {"xiaohongshu-mcp": {"token": "secret"}}}), encoding="utf-8")
            with self.assertRaises(ConfigError):
                load_config(path)


if __name__ == "__main__":
    unittest.main()
