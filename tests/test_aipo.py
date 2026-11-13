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


class ResearchCase(unittest.TestCase):
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

class ServiceCase(ResearchCase):
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


class ModelAndPriceTests(ResearchCase):
    def test_configured_model_plans_selects_and_cites(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        calls = {"detail": [], "keyword": None}

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):
                return

            def _json(self, payload, code=200):
                raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self):
                if self.path == "/health":
                    self._json({"success": True, "data": {"version": "stub-xhs"}})
                elif self.path == "/api/v1/login/status":
                    self._json({"data": {"is_logged_in": True}})
                else:
                    self._json({"ok": False}, 404)

            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                if self.path == "/v1/chat/completions":
                    system = body["messages"][0]["content"]
                    user = body["messages"][1]["content"]
                    if "研究规划器" in system:
                        content = json.dumps({"keywords": ["门店表格汇总"], "keep_sources": ["xiaohongshu-mcp"]}, ensure_ascii=False)
                    elif "值得深读" in system:
                        content = json.dumps({"ids": ["note-b"]}, ensure_ascii=False)
                    else:
                        import re
                        found = re.findall(r"\[(E[a-f0-9]{16})\]", user)
                        content = (
                            "目标客户是留下这条材料的人 [%s]。反例尚未单独成段。"
                            "没有挂牌价。没有成交证据。最小付费验证是先向对方报价。停止条件是无人付款。"
                        ) % found[0]
                    self._json({"choices": [{"message": {"content": content}}]})
                    return
                if self.path == "/api/v1/feeds/search":
                    calls["keyword"] = body.get("keyword")
                    self._json({"feeds": [
                        {"id": "note-a", "xsecToken": "token-a", "noteCard": {"displayTitle": "先不要读"}},
                        {"id": "note-b", "xsecToken": "token-b", "noteCard": {"displayTitle": "值得深读的门店表格"}},
                    ]})
                    return
                if self.path == "/api/v1/feeds/detail":
                    calls["detail"].append(body.get("feed_id"))
                    self._json({"data": {"note": {"noteId": body.get("feed_id"), "title": "值得深读的门店表格", "desc": "想找人做汇总。"}, "comments": {"list": []}}})
                    return
                self._json({"ok": False}, 404)

        model_server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        xhs_server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threads = []
        for server in (model_server, xhs_server):
            thread = __import__("threading").Thread(target=server.serve_forever, daemon=True)
            thread.start()
            threads.append(thread)
        os.environ["AIPO_MODEL_API_KEY"] = "test-key"
        live = None
        try:
            live = self.make("live", source_timeout_seconds=8, model={
                "base_url": "http://127.0.0.1:%s/v1" % model_server.server_address[1],
                "name": "stub-model",
                "timeout_seconds": 5,
            }, projects={
                "xiaohongshu-mcp": {"service_url": "http://127.0.0.1:%s" % xhs_server.server_address[1]},
            })
            view = self.finish(QUESTION, ["小红书"], service=live)
        finally:
            os.environ.pop("AIPO_MODEL_API_KEY", None)
            model_server.shutdown()
            xhs_server.shutdown()
            model_server.server_close()
            xhs_server.server_close()
            if live is not None:
                live.close()
        self.assertEqual(view["status"], "已完成")
        self.assertEqual(calls["keyword"], "门店表格汇总")
        self.assertEqual(calls["detail"], ["note-b"])
        self.assertIn("门店表格汇总", view["report_markdown"])
        self.assertIn("没有成交证据", view["report_markdown"])
        self.assertIn("目标客户是留下这条材料的人", view["report_markdown"])
        self.assertTrue(any(item["kind"] == "model_plan" for item in view["events"]))
        self.assertTrue(any(item["kind"] == "model_select" for item in view["events"]))
        self.assertTrue(any(item["kind"] == "model_report" for item in view["events"]))
        source = view["sources"][0]
        self.assertEqual(source["read_depth"], "2 张卡片，深读 1 篇")
        self.assertEqual(source["version"], "stub-xhs")
        self.assertIn("先不要读", view["report_markdown"])
        self.assertNotIn("模型补充", view["report_markdown"])

    def test_goofish_detail_keeps_listing_apart_from_platform_status(self):
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        log = self.root / "goofish.log"
        script = bin_dir / "goofish"
        script.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, sys\n"
            "open(os.environ['GOOFISH_LOG'], 'a', encoding='utf-8').write(' '.join(sys.argv[1:]) + '\\n')\n"
            "args = sys.argv[1:]\n"
            "if args[:2] == ['auth', 'status']:\n"
            "    print(json.dumps({'valid': True, 'unb': 'SHOULD_NOT_LEAK'}))\n"
            "    raise SystemExit(0)\n"
            "if args[:2] == ['search', 'items']:\n"
            "    print(json.dumps({'items': [\n"
            "        {'item_id': '1001', 'title': '只挂牌', 'price': '¥9.90', 'url': 'https://example.invalid/xianyu/1001'},\n"
            "        {'item_id': '1002', 'title': '页面写着已售', 'price': '¥20', 'url': 'https://example.invalid/xianyu/1002', 'badge': '已售出'}\n"
            "    ]}))\n"
            "    raise SystemExit(0)\n"
            "if args[:2] == ['item', 'get'] and args[2] == '1002':\n"
            "    print(json.dumps({'item_id': '1002', 'title': '页面写着已售', 'price': '20', 'price_kind': 'fixed', 'status': '已售出', 'description': '卖家说已经卖掉'}))\n"
            "    raise SystemExit(0)\n"
            "raise SystemExit(1)\n",
            encoding="utf-8",
        )
        script.chmod(0o755)
        old_path = os.environ.get("PATH", "")
        os.environ["PATH"] = str(bin_dir) + os.pathsep + old_path
        os.environ["GOOFISH_LOG"] = str(log)
        live = self.make("live", source_timeout_seconds=8)
        try:
            live.plan_override = lambda question, planned: {"keywords": ["门店表格汇总"], "keep_sources": ["goofish-cli"]}
            live.select_override = lambda question, cards, limit: ["1002"]
            view = self.finish("帮我看闲鱼上的表格处理供给", ["闲鱼"], service=live)
        finally:
            os.environ["PATH"] = old_path
            os.environ.pop("GOOFISH_LOG", None)
            live.close()
        commands = log.read_text(encoding="utf-8").splitlines()
        self.assertIn("auth status --format json", commands)
        self.assertTrue(any(line.startswith("search items 门店表格汇总") for line in commands))
        self.assertIn("item get 1002 --format json", commands)
        self.assertFalse(any(line.startswith("item get 1001") for line in commands))
        report = view["report_markdown"]
        self.assertIn("挂牌价 9.90", report)
        self.assertIn("挂牌价 20", report)
        self.assertIn("平台公开标记", report)
        self.assertIn("卖家自述", report)
        self.assertIn("没有独立核验成交", report)
        self.assertNotIn("独立核验成交：", report)
        self.assertNotIn("SHOULD_NOT_LEAK", report)
        archive = Path(view["archive_path"])
        blob = "\n".join(path.read_text(encoding="utf-8") for path in archive.rglob("*") if path.is_file())
        self.assertNotIn("SHOULD_NOT_LEAK", blob)
        source = next(item for item in view["sources"] if item["source"] == "goofish-cli")
        self.assertEqual(source["read_depth"], "2 条挂牌，详情 1 条")
        self.assertEqual(view["status"], "已完成")

    def test_verified_transaction_is_not_a_listing(self):
        from aipo.report import build_brief
        aggregate = {"evidence": [{
            "id": "Eaaaaaaaaaaaaaaaa",
            "url": "https://example.invalid/deal",
            "platform": "闲鱼",
            "observations": [{
                "title": "已核对订单",
                "summary": "独立核验成交：成交价 20。挂牌价 9.9。",
                "access": "product",
                "path": "live:goofish-cli/in-site/search",
                "archived_at": "2026-11-13T00:00:00+08:00",
            }],
        }]}
        brief, _cards = build_brief("核对一笔价格", aggregate, [], {"keywords": ["价格"], "budget": {}}, "replay")
        self.assertIn("挂牌价 9.9", brief)
        self.assertIn("成交证据：", brief)
        self.assertIn("两类证据", brief)
        self.assertNotIn("没有独立核验成交", brief)


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
        for row in report["providers"]:
            if not row["present"]:
                self.assertTrue(all(not item["match"] for item in row["files"]))
            else:
                self.assertTrue(row["files"])
                self.assertTrue(all(item["match"] for item in row["files"]))
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

    def test_doctor_command_is_callable(self):
        from aipo.__main__ import main
        import io
        from contextlib import redirect_stdout
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = main(["doctor"])
        self.assertEqual(code, 0)
        self.assertIn("xiaohongshu-mcp", buffer.getvalue())

    def test_config_rejects_secrets(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "local.json"
            path.write_text(json.dumps({"projects": {"xiaohongshu-mcp": {"token": "secret"}}}), encoding="utf-8")
            with self.assertRaises(ConfigError):
                load_config(path)


if __name__ == "__main__":
    unittest.main()
