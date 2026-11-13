"""实采与导入。失败保持真实原因，不用回放夹具填补。"""

import csv
import io
import json
import re
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

from aipo.config import repo_root
from aipo.contract import SourceResult, evidence_item, result

IMPORT_FILES = {
    "MediaCrawler": "mediacrawler-comments.jsonl",
    "social-media-copilot": "copilot-export.json",
    "ai-goofish-monitor": "goofish-monitor.csv",
}
IMPORT_PLATFORM = {
    "MediaCrawler": "小红书",
    "social-media-copilot": "快手",
    "ai-goofish-monitor": "闲鱼",
}
CN_KEYS = {
    "bilibili": ("B站", "in-site"),
    "weibo": ("微博", "in-site"),
    "zhihu": ("知乎", "in-site"),
    "douyin": ("抖音", "in-site"),
    "xiaohongshu": ("小红书", "in-site"),
    "wechat": ("微信公众号", "in-site"),
    "wxmp": ("微信公众号", "in-site"),
    "baidu": ("百度", "public-index"),
    "toutiao": ("今日头条", "public-index"),
    "web": ("网页", "public-index"),
}


class HttpError(OSError):
    pass


def http_json(method, url, payload=None, timeout=8):
    data = None
    headers = {"Accept": "application/json", "User-Agent": "aipo-research"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None

    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=timeout) as response:
            body = response.read(2 * 1024 * 1024)
    except urllib.error.HTTPError as exc:
        raise HttpError("HTTP %s" % exc.code) from exc
    except TimeoutError as exc:
        raise TimeoutError("请求超时") from exc
    except OSError as exc:
        raise HttpError("服务未连通") from exc
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HttpError("响应不是 JSON") from exc


def run_command(args, timeout, cwd=None):
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout, cwd=cwd, check=False)
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError("命令超时") from exc
    except OSError as exc:
        raise HttpError(exc.strerror or "命令无法启动") from exc


def _note_url(note_id, explicit=None):
    if isinstance(explicit, str) and explicit.startswith(("http://", "https://")):
        return explicit
    return "https://www.xiaohongshu.com/explore/%s" % note_id


def _walk_feeds(payload):
    found = []

    def visit(node, depth):
        if depth > 6:
            return
        if isinstance(node, dict):
            feeds = node.get("feeds")
            if isinstance(feeds, list):
                found.extend(item for item in feeds if isinstance(item, dict))
            for value in node.values():
                visit(value, depth + 1)
        elif isinstance(node, list):
            for value in node[:30]:
                visit(value, depth + 1)

    visit(payload, 0)
    return found


def _detail_parts(payload):
    found = {}

    def visit(node, depth):
        if depth > 6 or found:
            return
        if isinstance(node, dict) and isinstance(node.get("note"), dict):
            found["note"] = node["note"]
            found["comments"] = node.get("comments")
            return
        if isinstance(node, dict):
            for value in node.values():
                visit(value, depth + 1)

    visit(payload, 0)
    return found.get("note"), found.get("comments")


def _comment_nodes(comments):
    if isinstance(comments, dict):
        rows = comments.get("list") or []
        more = comments.get("hasMore")
    elif isinstance(comments, list):
        rows = comments
        more = None
    else:
        rows = []
        more = None
    flat = []
    for row in rows:
        if isinstance(row, dict):
            flat.append(row)
            for sub in row.get("subComments") or []:
                if isinstance(sub, dict):
                    flat.append(sub)
    return flat, more


def _listing_amount(value):
    if value is None:
        return None
    text = str(value).replace("¥", "").replace("￥", "").replace(",", "").strip()
    if re.fullmatch(r"\d+(?:\.\d+)?", text):
        return text
    return None


def _sold_status(status):
    text = str(status or "")
    lowered = text.lower()
    return any(word in text or word in lowered for word in ("已售", "售出", "卖掉", "已卖出", "sold"))


def collect_xiaohongshu(config, keyword, timeout, select=None):
    base = config.service_url("xiaohongshu-mcp", "http://127.0.0.1:18060")
    path = "live:xiaohongshu-mcp/in-site"
    try:
        health = http_json("GET", base + "/health", timeout=min(4, timeout))
        login = http_json("GET", base + "/api/v1/login/status", timeout=min(4, timeout))
    except TimeoutError:
        return result("xiaohongshu-mcp", "live", "timeout", "小红书", path + "/health", "小红书服务超时。未写入笔记。", registration="受阻")
    except HttpError as exc:
        return result("xiaohongshu-mcp", "live", "error", "小红书", path + "/health", "小红书服务未连通：%s。未写入笔记。" % exc, registration="受阻")
    if not isinstance(health, dict) or health.get("success") is not True:
        return result("xiaohongshu-mcp", "live", "error", "小红书", path + "/health", "健康检查不符合 success 契约。未搜索。", raw={"health": health}, registration="受阻")
    logged = login.get("data", {}).get("is_logged_in") if isinstance(login, dict) else None
    if logged is False:
        return result("xiaohongshu-mcp", "live", "need_login", "小红书", path + "/login", "服务可达，但当前没有有效登录。未搜索。", raw={"login": {"is_logged_in": False}}, registration="受阻")
    if logged is not True:
        return result("xiaohongshu-mcp", "live", "unknown", "小红书", path + "/login", "登录状态无法判断。未搜索。", registration="受阻")
    try:
        search = http_json("POST", base + "/api/v1/feeds/search", {"keyword": keyword}, timeout=timeout)
    except TimeoutError:
        return result("xiaohongshu-mcp", "live", "timeout", "小红书", path + "/search", "搜索超时。", registration="受阻")
    except HttpError as exc:
        return result("xiaohongshu-mcp", "live", "error", "小红书", path + "/search", "搜索失败：%s" % exc, registration="受阻")
    feeds = _walk_feeds(search)
    version = None
    if isinstance(health.get("data"), dict):
        version = health["data"].get("version")
    if not feeds:
        return result("xiaohongshu-mcp", "live", "empty", "小红书", path + "/search", "搜索成功，但没有可解析的笔记卡片。",
                      raw={"search": search}, version=version if isinstance(version, str) else None, read_depth="0 篇", registration="实采")
    evidence = []
    details = []
    cards = []
    for feed in feeds:
        note_id = str(feed.get("id") or feed.get("noteId") or "")
        token = feed.get("xsecToken") or feed.get("xsec_token")
        card = feed.get("noteCard") if isinstance(feed.get("noteCard"), dict) else {}
        title = card.get("displayTitle") or feed.get("title") or note_id or "未命名笔记"
        if note_id:
            cards.append({"id": note_id, "title": str(title), "has_token": bool(token)})
    chosen = select(cards, 6) if select is not None else None
    chosen_set = set(chosen) if chosen else None
    for index, feed in enumerate(feeds):
        note_id = str(feed.get("id") or feed.get("noteId") or "")
        token = feed.get("xsecToken") or feed.get("xsec_token")
        card = feed.get("noteCard") if isinstance(feed.get("noteCard"), dict) else {}
        title = card.get("displayTitle") or feed.get("title") or note_id or "未命名笔记"
        if not note_id:
            continue
        should_read = bool(token) and (note_id in chosen_set if chosen_set is not None else index < 6)
        if not should_read:
            evidence.append(evidence_item(
                _note_url(note_id, feed.get("url")), "小红书", str(title),
                "搜索卡片。未读正文。实采。", path + "/search", "link",
            ))
            continue
        try:
            detail = http_json("POST", base + "/api/v1/feeds/detail", {
                "feed_id": note_id, "xsec_token": token, "load_all_comments": False,
            }, timeout=timeout)
        except (TimeoutError, HttpError) as exc:
            evidence.append(evidence_item(
                _note_url(note_id), "小红书", str(title),
                "详情读取失败：%s。实采只保留搜索卡片。" % type(exc).__name__, path + "/search", "link",
            ))
            continue
        details.append({"feed_id": note_id, "detail": detail})
        note, comments = _detail_parts(detail)
        note = note or {}
        note_url = _note_url(note.get("noteId") or note_id)
        desc = note.get("desc") or note.get("title") or title
        evidence.append(evidence_item(note_url, "小红书", str(note.get("title") or title), "讨论正文：%s" % desc, path + "/detail", "body"))
        flat, _more = _comment_nodes(comments)
        for comment in flat[:20]:
            content = comment.get("content") or ""
            cid = str(comment.get("id") or len(evidence))
            if not content:
                continue
            evidence.append(evidence_item(
                note_url + "#comment-" + cid, "小红书", "评论：" + content, "评论原文：%s" % content,
                path + "/detail", "comments",
            ))
    depth = "%s 张卡片，深读 %s 篇" % (len(feeds), len(details))
    reason = "实采只读搜索和详情。访问令牌留在原件，报告链接不含令牌。未翻页。"
    if len(feeds) > 6:
        reason += " 超过 6 篇的卡片只保留搜索摘要。"
    return result("xiaohongshu-mcp", "live", "success", "小红书", path + "/search+detail", reason,
                  evidence=evidence, raw={"search": search, "details": details}, version=version if isinstance(version, str) else None,
                  read_depth=depth, registration="实采")


def _parse_goofish_items(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        if payload.get("requiresAuth") is True or payload.get("error") in ("auth_required", "need_login"):
            return "auth"
        for key in ("items", "data", "result"):
            if key in payload:
                parsed = _parse_goofish_items(payload[key])
                if parsed == "auth" or parsed:
                    return parsed
    return []


def _json_stdout(proc):
    try:
        value = json.loads(proc.stdout or "")
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _goofish_url(item):
    url = item.get("url") or item.get("link")
    if isinstance(url, str) and url.startswith(("http://", "https://")):
        return url
    item_id = str(item.get("item_id") or item.get("id") or "")
    if item_id.isdigit():
        return "https://www.goofish.com/item?id=%s" % item_id
    return ""


def _listing_sentence(price):
    amount = _listing_amount(price)
    if amount is None:
        return "挂牌价未知。"
    return "挂牌价 %s。未核验成交。" % amount


def _goofish_summary(item, detail):
    parts = ["供给。", _listing_sentence((detail or {}).get("price") if detail else item.get("price"))]
    if detail:
        kind = {"fixed": "一口价", "negotiable": "可议价"}.get(detail.get("price_kind"), "未知")
        parts.append("标价类型：%s。" % kind)
        original = _listing_amount(detail.get("original_price"))
        if original:
            parts.append("原价标记 %s，不是成交价。" % original)
        status = detail.get("status")
        if _sold_status(status):
            parts.append("平台公开标记：商品状态为%s。这不是独立核验成交。" % status)
        elif status:
            parts.append("平台状态：%s。这是在售或未知状态，不是成交记录。" % status)
        else:
            parts.append("平台状态未知。")
        description = " ".join(str(detail.get("description") or "").split())
        if description:
            parts.append("卖家自述：%s。" % description[:120])
    else:
        badge = " ".join(str(item.get("badge") or "").split())
        if _sold_status(badge):
            parts.append("平台公开标记：搜索卡片标记为%s。这不是独立核验成交。" % badge[:40])
        parts.append("未读详情。")
    parts.append("实采。")
    return "".join(parts)


def collect_goofish(keyword, timeout, select=None):
    binary = shutil.which("goofish")
    path = "live:goofish-cli/in-site"
    if not binary:
        return result("goofish-cli", "live", "missing_dependency", "闲鱼", path,
                      "未找到 goofish 命令。没有查询商品。指纹对应的入口是 v0.6.0。", registration="受阻")
    try:
        auth = run_command([binary, "auth", "status", "--format", "json"], timeout=min(timeout, 8))
    except TimeoutError:
        return result("goofish-cli", "live", "timeout", "闲鱼", path + "/auth", "登录检查超时。未搜索商品。", registration="受阻")
    auth_payload = _json_stdout(auth)
    if auth.returncode != 0 or not auth_payload or auth_payload.get("valid") is not True:
        return result("goofish-cli", "live", "need_login", "闲鱼", path + "/auth",
                      "auth status 未确认有效登录。未搜索商品。", raw={"valid": False}, registration="受阻")
    try:
        proc = run_command([binary, "search", "items", keyword, "--limit", "5", "--format", "json"], timeout=timeout)
    except TimeoutError:
        return result("goofish-cli", "live", "timeout", "闲鱼", path + "/search", "闲鱼搜索超时。", registration="受阻")
    payload = _json_stdout(proc)
    if payload is None:
        return result("goofish-cli", "live", "degraded" if proc.returncode == 0 else "error", "闲鱼", path + "/search",
                      "搜索输出不是 JSON。原件已保留，没有编造商品。",
                      raw={"returncode": proc.returncode, "stdout": (proc.stdout or "")[:4000]},
                      read_depth="0 条可解析商品", registration="实采" if proc.returncode == 0 else "受阻")
    errors = [item for item in payload.get("errors") or [] if isinstance(item, dict)]
    if any(item.get("error_type") == "authentication_required" for item in errors) or payload.get("requiresAuth") is True:
        return result("goofish-cli", "live", "need_login", "闲鱼", path + "/search", "搜索结果要求登录。", raw={"valid": False}, registration="受阻")
    if any(item.get("error_type") == "blocked" for item in errors):
        return result("goofish-cli", "live", "blocked", "闲鱼", path + "/search", "搜索被平台拦截。未采用商品。", registration="受阻")
    parsed = _parse_goofish_items(payload)
    if parsed == "auth":
        return result("goofish-cli", "live", "need_login", "闲鱼", path + "/search", "搜索结果要求登录。", raw={"valid": False}, registration="受阻")
    items = [item for item in list(parsed)[:5] if isinstance(item, dict)]
    cards = []
    for item in items:
        item_id = str(item.get("item_id") or item.get("id") or "")
        if item_id:
            cards.append({"id": item_id, "title": str(item.get("title") or item_id)})
    chosen = select(cards, 5) if select is not None else None
    chosen_ids = set(chosen) if chosen else {card["id"] for card in cards}
    evidence = []
    details = []
    detail_count = 0
    for item in items:
        url = _goofish_url(item)
        title = item.get("title") or item.get("item_id") or item.get("id")
        if not url or not title:
            continue
        item_id = str(item.get("item_id") or item.get("id") or "")
        detail = None
        if item_id.isdigit() and item_id in chosen_ids:
            try:
                detail_proc = run_command([binary, "item", "get", item_id, "--format", "json"], timeout=min(timeout, 8))
                detail = _json_stdout(detail_proc) if detail_proc.returncode == 0 else None
            except TimeoutError:
                detail = None
            if detail:
                detail_count += 1
                details.append({"item_id": item_id, "detail": {key: value for key, value in detail.items() if key != "raw"}})
        evidence.append(evidence_item(url, "闲鱼", str(title), _goofish_summary(item, detail), path + "/search+item-get", "product"))
    status = "success" if evidence else "empty"
    if proc.returncode != 0 and evidence:
        status = "degraded"
    depth = "%s 条挂牌，详情 %s 条" % (len(evidence), detail_count)
    reason = "实采商品搜索后按预算读取详情。挂牌价不是成交价。登录标识未写入原件。"
    return result("goofish-cli", "live", status, "闲鱼", path + "/search+item-get", reason,
                  evidence=evidence, raw={"search": payload, "details": details, "auth_valid": True},
                  read_depth=depth, registration="实采")


def _script(path):
    return path.is_file()


def collect_last30days(config, source, topic, timeout, search, hot=False):
    if source == "last30days-skill-cn":
        root = config.project_path(source, "upstream/last30days-skill-cn")
        script = root / "scripts" / "last30days.py"
        version = "af785c6"
        command_search = ["--search", "cn"]
    else:
        root = config.project_path(source, "upstream/last30days-skill")
        script = root / "skills" / "last30days" / "scripts" / "last30days.py"
        version = "3.30.0"
        command_search = ["--search", search or "reddit,hackernews"]
    path = "live:%s" % source
    if not _script(script):
        return result(source, "live", "missing_dependency", "检索", path,
                      "未找到 %s。没有执行检索。" % script.name, registration="受阻")
    python = shutil.which("python3") or "python3"
    args = [python, str(script), topic, "--emit", "json", "--days", "30", *command_search]
    if hot and source == "last30days-skill-cn":
        args = [python, str(script), "--hot", "--emit", "json"]
    try:
        proc = run_command(args, timeout=timeout, cwd=str(root))
    except TimeoutError:
        return result(source, "live", "timeout", "检索", path, "检索命令超时。", version=version, registration="受阻")
    raw_text = proc.stdout or ""
    if proc.returncode != 0:
        return result(source, "live", "error", "检索", path, "检索命令失败。",
                      raw={"returncode": proc.returncode, "stderr": (proc.stderr or "")[:800]}, version=version, registration="受阻")
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError:
        return result(source, "live", "degraded", "检索", path, "命令有输出但不是 JSON。未编造条目。",
                      raw={"stdout": raw_text[:4000]}, version=version, read_depth="未解析", registration="实采")
    channels, evidence = parse_research_json(payload, "live:%s" % source)
    if not channels:
        channels = [{"platform": "检索", "status": "empty" if not evidence else "success", "path": path, "reason": "实采 JSON 已归档。"}]
    for channel in channels:
        channel["reason"] = "实采输出。公开索引与站内按字段标注。"
    return SourceResult(source, version, "live", channels, evidence, payload, source + ".json",
                        "%s 条可定位链接" % len(evidence), registration="实采")


def parse_research_json(payload, path_base):
    channels = []
    evidence = []
    if not isinstance(payload, dict):
        return channels, evidence
    status = payload.get("source_status") if isinstance(payload.get("source_status"), dict) else {}
    for key, rows in payload.items():
        if key == "source_status" or not isinstance(rows, list):
            continue
        platform, site = CN_KEYS.get(key, (key, "in-site"))
        state = (status.get(key) or {}).get("state")
        mapped = {"ok": "success", "empty": "empty", "timeout": "timeout"}.get(state, "success" if rows else "empty")
        item_path = "%s/%s/%s" % (path_base, "public-index" if site == "public-index" else "in-site", key)
        channels.append({"platform": platform, "status": mapped, "path": item_path, "reason": ""})
        for row in rows:
            if not isinstance(row, dict):
                continue
            url = row.get("url")
            title = row.get("title")
            if not isinstance(url, str) or not url.startswith(("http://", "https://")) or not title:
                continue
            published = row.get("date") if isinstance(row.get("date"), str) else None
            confidence = row.get("date_confidence") if published and row.get("date_confidence") in ("high", "medium", "low") else ("unknown" if not published else "low")
            evidence.append(evidence_item(url, platform, str(title), "检索摘要，未默认补读正文。", item_path, "link", published, confidence))
    return channels, evidence


def collect_agent_reach(url, timeout):
    binary = shutil.which("agent-reach")
    path = "live:Agent-Reach/read"
    if not binary:
        return result("Agent-Reach", "live", "missing_dependency", "网页", path, "未找到 agent-reach 命令。未补读。", registration="受阻")
    try:
        proc = run_command([binary, "read", url], timeout=timeout)
    except TimeoutError:
        return result("Agent-Reach", "live", "timeout", "网页", path, "补读超时。", registration="受阻")
    text = (proc.stdout or "")[:8000]
    if proc.returncode != 0:
        lowered = (proc.stderr or "").lower()
        status = "need_login" if "need_login" in lowered or "login" in lowered else "error"
        return result("Agent-Reach", "live", status, "网页", path, "补读命令失败。", raw={"stderr": (proc.stderr or "")[:500]}, registration="受阻")
    if not text.strip():
        return result("Agent-Reach", "live", "empty", "网页", path, "补读没有正文。", registration="实采")
    evidence = [evidence_item(url, "网页", "补读 " + url, "实采补读摘录：" + text[:240], path, "body")]
    return result("Agent-Reach", "live", "success", "网页", path, "实采补读。摘录不是全文，原件保留命令输出。",
                  evidence=evidence, raw={"stdout": text}, version="1.6.0", read_depth="命令输出", registration="实采")


def _rows_from_export(path: Path):
    text = path.read_text(encoding="utf-8-sig")
    suffix = path.suffix.lower()
    if suffix == ".csv":
        rows = list(csv.DictReader(io.StringIO(text)))
        return rows, text
    if suffix == ".jsonl":
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
        return rows, text
    payload = json.loads(text)
    if isinstance(payload, dict) and isinstance(payload.get("items"), list):
        return payload["items"], text
    if isinstance(payload, list):
        return payload, text
    return [payload], text


def _import_result(source, file_path, mode):
    platform = IMPORT_PLATFORM[source]
    prefix = "replay" if mode == "replay" else "import"
    path = "%s:%s/import" % (prefix, source)
    license_note = ""
    if source == "MediaCrawler":
        license_note = "许可证仅限非商业学习。本次没有启动爬虫。"
    if file_path is None or not file_path.is_file():
        return result(source, "live" if mode == "live" else "replay", "missing_dependency", platform, path,
                      "没有可导入文件。%s" % license_note, registration="受阻" if mode == "live" else "回放")
    try:
        rows, _text = _rows_from_export(file_path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, csv.Error) as exc:
        return result(source, mode if mode != "replay" else "replay", "error", platform, path,
                      "导出文件无法解析：%s。%s" % (type(exc).__name__, license_note), registration="受阻")
    evidence = []
    access = "monitor_result" if source == "ai-goofish-monitor" else "comments" if source == "MediaCrawler" else "link"
    for row in rows:
        if not isinstance(row, dict):
            continue
        url = row.get("url") or row.get("link") or row.get("商品链接")
        title = row.get("title") or row.get("标题") or "导入材料"
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            continue
        comment = row.get("comment") or row.get("content") or row.get("note") or row.get("备注") or ""
        price = row.get("price") or row.get("价格")
        summary = "导入原文：%s" % comment
        if price not in (None, ""):
            summary += "。挂牌价 %s。未核验成交。" % price
        if "example.invalid" in url:
            summary += " 链接是合成夹具，不是用户实导出。"
        if mode == "replay":
            summary += " 回放读取仓库夹具，不是实采。"
        else:
            summary += " 这是导入，不是站内实采。"
        evidence.append(evidence_item(url, str(row.get("platform") or platform), str(title), summary, path, access))
    status = "success" if evidence else "empty"
    reason = "已导入 %s。%s %s" % (file_path.name, license_note, "回放夹具。" if mode == "replay" else "不是实采。")
    registration = "回放" if mode == "replay" else "导入"
    return SourceResult(
        tool=source,
        version=None,
        mode="replay" if mode == "replay" else "import",
        channels=[{"platform": platform, "status": status, "path": path, "reason": reason}],
        evidence=evidence,
        raw={"file": file_path.name, "rows": rows, "registration": registration},
        raw_name=source + "-import.json",
        read_depth="%s 条可定位导入" % len(evidence),
        registration=registration,
    )


def import_fixture(source, mode="replay"):
    file_path = repo_root() / "aipo" / "fixtures" / IMPORT_FILES[source]
    return _import_result(source, file_path, mode)


def collect_import(config, source, mode):
    if mode == "replay":
        return import_fixture(source, "replay")
    return _import_result(source, config.import_path(source), "live")


def collect_host_web():
    return result("host-web", "live", "blocked", "网页", "live:host-web/public-clue",
                  "本服务不内置网页抓取，没有把公开索引写成已读取。", registration="受阻")


def collect(job, config, attempt, task_kind, select=None):
    del attempt, task_kind
    source = job["source"]
    keyword = job["keywords"][0] if job["keywords"] else "商机"
    timeout = config.source_timeout_seconds
    if source == "unregistered":
        platform = job["platforms"][0] if job["platforms"] else "未登记"
        return result("host-web", "live", "blocked", platform, "live:unregistered", "未登记平台，未调用上游。", registration="受阻")
    if source == "xiaohongshu-mcp":
        return collect_xiaohongshu(config, keyword, timeout, select=select)
    if source == "goofish-cli":
        return collect_goofish(keyword, timeout, select=select)
    if source in ("last30days-skill-cn", "last30days-skill"):
        search = "cn" if source.endswith("-cn") else "reddit,hackernews"
        return collect_last30days(config, source, keyword, timeout, search, hot="hot" in job["capabilities"])
    if source == "Agent-Reach":
        target = job["urls"][0] if job["urls"] else ""
        if not target:
            return result(source, "live", "blocked", "网页", "live:Agent-Reach/read", "没有给定链接，未补读。", registration="受阻")
        return collect_agent_reach(target, timeout)
    if source in IMPORT_FILES:
        return collect_import(config, source, "live")
    if source == "host-web":
        return collect_host_web()
    return result(source, "live", "blocked", source, "live:%s" % source, "没有实采适配。未伪造结果。", registration="受阻")
