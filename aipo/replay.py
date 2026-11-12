"""回放夹具。内容是合成的，登记为回放，不能当成实采。"""

import json
from pathlib import Path

from aipo.config import repo_root
from aipo.contract import evidence_item, result
from aipo.triggers import kind

REPLAY = "回放样本，不是实采。"
XHS_VERSION = "response-shape-v2.7.0;replay"


def _sample():
    path = repo_root() / "docs" / "回放样例.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _loads_content(block):
    return json.loads(block["content"][0]["text"])


def xhs_evidence(path):
    sample = _sample()
    detail = _loads_content(sample["xiaohongshu"]["detail_result"])
    note = detail["data"]["note"]
    comments = detail["data"]["comments"]["list"]
    note_url = "https://example.invalid/xiaohongshu/note/%s" % note["noteId"]
    items = [evidence_item(
        note_url, "小红书", note["title"],
        "讨论正文：%s %s" % (note["desc"], REPLAY),
        path, "body",
    )]
    for comment in comments:
        items.append(evidence_item(
            note_url + "#comment-" + comment["id"],
            "小红书",
            "评论：" + comment["content"],
            "评论原文：%s %s" % (comment["content"], REPLAY),
            path, "comments",
        ))
    raw = {"xiaohongshu": sample["xiaohongshu"], "registration": "回放", "source_file": "docs/回放样例.json"}
    return items, raw


def goofish_evidence(path):
    sample = _sample()
    items = []
    for obs in sample["goofish"]["normalized_observations"]:
        items.append(evidence_item(
            obs["source_url"], "闲鱼", obs["title"],
            "供给挂牌。挂牌价 %s %s。%s 成交未核验。%s" % (
                obs["asking_price"], obs["currency"], obs["price_note"], REPLAY),
            path, "product",
        ))
    raw = {"goofish": sample["goofish"], "registration": "回放", "source_file": "docs/回放样例.json"}
    return items, raw


def _cn_items(platforms, path_base):
    bilibili = evidence_item(
        "https://example.invalid/bilibili/replay-1", "B站", "开源表格脚本演示",
        "站内检索摘要，未读字幕或评论。%s" % REPLAY,
        path_base + "/in-site/wbi-search", "link",
    )
    baidu = evidence_item(
        "https://example.invalid/baidu/replay-1", "百度", "公开索引里的表格软件入口",
        "公开索引条目，不是站内正文。%s" % REPLAY,
        path_base + "/public-index/baidu", "link",
    )
    chosen = []
    names = set(platforms)
    if not names or "中文检索" in names or "B站" in names:
        chosen.append(bilibili)
    if not names or "中文检索" in names or "百度" in names:
        chosen.append(baidu)
    if names and "中文检索" not in names and "B站" not in names and "百度" not in names:
        chosen = []
    return chosen


def _global_items(path_base):
    return [
        evidence_item(
            "https://example.invalid/hackernews/replay-1", "Hacker News", "Show HN: spreadsheet merge script",
            "海外站内检索摘要，未读评论。%s" % REPLAY,
            path_base + "/in-site/hackernews", "link",
        ),
        evidence_item(
            "https://example.invalid/web/replay-1", "网页", "公开网页上的表格工具目录",
            "公开索引，不是论坛原帖。%s" % REPLAY,
            path_base + "/public-index/web", "link",
        ),
    ]


def _thin(platform, path):
    return [evidence_item(
        "https://example.invalid/thin/%s" % platform, platform, "只有一条公开摘要",
        "索引标题提到相关工具，没有正文、评论或价格。%s" % REPLAY,
        path, "link",
    )]


def _channels(items, default_platform, path, reason, status="success"):
    if not items:
        return [{"platform": default_platform, "status": status, "path": path, "reason": reason}]
    grouped = {}
    for item in items:
        grouped.setdefault(item["path"], item["platform"])
    return [
        {"platform": platform, "status": "success", "path": item_path, "reason": reason}
        for item_path, platform in grouped.items()
    ]


def collect(job, task_kind, attempt):
    source = job["source"]
    platform = job["platforms"][0] if job["platforms"] else source
    if source == "unregistered":
        return result("host-web", "replay", "blocked", platform, "replay:unregistered",
                      "未登记平台，没有回放夹具，也没有伪造结果。", registration="回放")
    if task_kind == "empty":
        return result(source, "replay", "empty", platform, "replay:%s/empty" % source,
                      "回放为空结果。请求已按夹具完成，没有条目。不是实采。")
    if task_kind == "insufficient" and source in ("last30days-skill-cn", "xiaohongshu-mcp", "host-web"):
        path = "replay:%s/public-index/thin" % source
        items = _thin(platform if platform != source else "中文检索", path)
        return result(source, "replay", "success", items[0]["platform"], path,
                      "回放只有摘要，证据不足。不是实采。", evidence=items, raw={"items": items, "registration": "回放"},
                      read_depth="1 条链接摘要，无正文无评论")
    if source == "xiaohongshu-mcp" and task_kind == "session_invalid" and attempt < 2:
        return result(source, "replay", "need_login", "小红书", "replay:xiaohongshu-mcp/login",
                      "回放模拟会话失效。没有笔记样本。不是实采登录失败。")
    if source == "xiaohongshu-mcp" and task_kind == "public_clue":
        return result(source, "replay", "need_login", "小红书", "replay:xiaohongshu-mcp/login",
                      "指定平台在回放中不可用。没有用其他站内样本顶替。")
    if source == "goofish-cli" and task_kind == "partial_timeout":
        return result(source, "replay", "timeout", "闲鱼", "replay:goofish-cli/timeout",
                      "回放模拟闲鱼超时。没有商品，也不是实采超时。")
    if source == "xiaohongshu-mcp":
        path = "replay:xiaohongshu-mcp/in-site/search+detail"
        items, raw = xhs_evidence(path)
        depth = "1 篇正文，%s 条评论" % sum(1 for item in items if item["access"] == "comments")
        reason = "回放覆盖搜索卡片形态、正文和评论。材料来自 docs/回放样例.json。不是实采。"
        if task_kind == "session_invalid":
            reason = "回放在模拟恢复后给出同一夹具。这不是用户重新登录后的实采。"
        return result(source, "replay", "success", "小红书", path, reason, evidence=items, raw=raw,
                      version=XHS_VERSION, read_depth=depth)
    if source == "goofish-cli":
        path = "replay:goofish-cli/in-site/normalized"
        items, raw = goofish_evidence(path)
        return result(source, "replay", "success", "闲鱼", path,
                      "标准化回放商品，不是 v0.6.0 原生响应，也不是实采。挂牌价不是成交价。",
                      evidence=items, raw=raw, version=None, read_depth="%s 条挂牌" % len(items))
    if source == "last30days-skill-cn":
        if "hot" in job["capabilities"] or task_kind == "hot":
            path = "replay:last30days-skill-cn/hot-snapshot"
            items = [evidence_item(
                "https://example.invalid/hot/replay-1", "热榜", "热榜快照：表格工具字样",
                "这是榜单快照，不是近 30 天主题讨论。%s" % REPLAY, path, "link",
            )]
            return result(source, "replay", "success", "热榜", path,
                          "回放热榜。不能用检索日期解释榜单热度。不是实采。",
                          evidence=items, raw={"items": items}, version="af785c6-replay", read_depth="1 条榜单")
        path = "replay:last30days-skill-cn"
        items = _cn_items(job["platforms"], path)
        if not items and task_kind == "primary":
            items = [evidence_item(
                "https://example.invalid/cn/replay-generic", "中文检索", "有人在问小工具能不能接小单",
                "检索摘要：想找人做个很小的工具，但没有预算和成交。%s" % REPLAY,
                path + "/in-site/generic", "link",
            )]
        channels = _channels(items, platform, path + "/empty", "回放没有该平台条目。")
        return _multi(source, "af785c6-replay", channels, items, "中文检索回放。公开索引与站内分开标注。不是实采。",
                      "链接摘要 %s 条，未读正文" % len(items))
    if source == "last30days-skill":
        path = "replay:last30days-skill"
        items = _global_items(path)
        channels = _channels(items, "海外检索", path, "海外回放。")
        return _multi(source, "3.30.0-replay", channels, items,
                      "海外检索回放。网页条目是公开索引。不是实采，也没有使用上游 --mock。",
                      "链接摘要 %s 条" % len(items))
    if source == "Agent-Reach":
        target = job["urls"][0] if job["urls"] else "https://example.invalid/docs/pricing"
        path = "replay:Agent-Reach/read"
        items = [evidence_item(
            target, "网页", "补读夹具",
            "回放正文：示例页只提到一次性配置费用，没有成交记录。未请求该网址。%s" % REPLAY,
            path, "body",
        )]
        return result(source, "replay", "success", "网页", path,
                      "原文补读回放。没有发出网络请求。",
                      evidence=items, raw={"url": target, "registration": "回放"},
                      version="1.6.0-replay", read_depth="夹具正文，非真实页面")
    if source == "host-web":
        path = "replay:host-web/public-clue"
        items = [evidence_item(
            "https://example.invalid/public-clue/1", "网页", "公开线索：表格工具介绍页",
            "公开线索，不能代替站内样本。%s" % REPLAY, path, "link",
        )]
        return result(source, "replay", "success", "网页", path,
                      "公开线索回放。指定平台不可用时，这条不能写成站内结果。",
                      evidence=items, raw={"registration": "回放"}, read_depth="1 条公开线索")
    if source in ("MediaCrawler", "social-media-copilot", "ai-goofish-monitor"):
        from aipo.live import import_fixture
        return import_fixture(source, mode="replay")
    return result(source, "replay", "blocked", platform, "replay:%s/missing" % source,
                  "没有该来源的回放夹具，未伪造结果。")


def _multi(tool, version, channels, items, reason, depth):
    if not items:
        channels = [{"platform": channels[0]["platform"], "status": "empty", "path": channels[0]["path"], "reason": reason}]
    else:
        for channel in channels:
            channel["reason"] = reason
    return result_from_channels(tool, version, channels, items, depth)


def result_from_channels(tool, version, channels, items, depth):
    from aipo.contract import SourceResult
    return SourceResult(
        tool=tool, version=version, mode="replay", channels=channels, evidence=items,
        raw={"evidence_preview": [item["title"] for item in items], "registration": "回放"},
        raw_name=tool + ".json", read_depth=depth, registration="回放",
    )


def task_kind(question):
    return kind(question)
