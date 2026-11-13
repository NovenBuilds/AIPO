"""按问题选择来源。未点名的平台不会被串行跑完。"""

from aipo.registry import IMPORT_SOURCES, PRIMARY, SOURCE_BY_ID, detect_platforms, normalize_platforms
from aipo.triggers import intent, kind, urls

SOURCE_CAPS = {
    "xiaohongshu-mcp": ["search", "body", "comments"],
    "goofish-cli": ["product"],
    "last30days-skill-cn": ["search"],
    "last30days-skill": ["search"],
    "Agent-Reach": ["read"],
    "MediaCrawler": ["import"],
    "social-media-copilot": ["import"],
    "ai-goofish-monitor": ["import"],
    "host-web": ["search"],
}


def keywords_for(question):
    text = " ".join((question or "").split())
    if "小程序" in text:
        return ["微信小程序 收费", "小程序 接单", "值得做的小程序方向"]
    if "表格" in text:
        return ["表格 自动化", "表格 付费"]
    compact = text[:40] or "商机"
    return [compact]


def _add(jobs, source, platform, capabilities):
    if source not in SOURCE_BY_ID and source != "unregistered":
        source = "unregistered"
    if source == "unregistered":
        jobs.append({
            "source": source,
            "platforms": [platform] if platform else [],
            "capabilities": list(capabilities),
        })
        return
    for job in jobs:
        if job["source"] == source:
            if platform and platform not in job["platforms"]:
                job["platforms"].append(platform)
            for cap in capabilities:
                if cap not in job["capabilities"]:
                    job["capabilities"].append(cap)
            return
    jobs.append({
        "source": source,
        "platforms": [platform] if platform else [],
        "capabilities": list(capabilities),
    })


def _number(jobs, question):
    keys = keywords_for(question)
    found = urls(question)
    for index, job in enumerate(jobs):
        job["ordinal"] = index
        job["keywords"] = keys
        job["urls"] = found
    return {
        "intent": intent(question),
        "kind": kind(question),
        "keywords": keys,
        "budget": {"max_notes": 30, "max_deep_reads": 6, "max_comments_per_note": 20, "max_products": 5, "keyword_groups": len(keys)},
        "jobs": jobs,
        "notes": [
            "首版每个来源只发一次搜索，避免三组关键词叠加后超过采样上限。",
            "同一平台只走主路径。",
        ],
    }


def _market(jobs):
    sources = {job["source"] for job in jobs}
    if "last30days-skill" in sources and "last30days-skill-cn" in sources:
        return "both"
    if sources == {"last30days-skill"}:
        return "global"
    if sources <= set(IMPORT_SOURCES) and sources:
        return "import"
    if sources == {"Agent-Reach"}:
        return "link"
    if sources == {"goofish-cli"}:
        return "product"
    if any(job["capabilities"] == ["hot"] for job in jobs):
        return "hot"
    return "cn"


def clamp_plan(question, planned, proposal):
    """收紧模型提案。不能新增来源，也不能删掉用户点名的平台。"""
    if not isinstance(proposal, dict) or not isinstance(planned, dict):
        return None
    raw_keys = proposal.get("keywords")
    if not isinstance(raw_keys, list) or not raw_keys:
        return None
    keywords = []
    for item in raw_keys[:3]:
        if not isinstance(item, str):
            return None
        text = " ".join(item.split())
        if not text or len(text) > 40:
            return None
        keywords.append(text)
    jobs = planned.get("jobs")
    if not isinstance(jobs, list) or not jobs:
        return None
    allowed = [job["source"] for job in jobs if isinstance(job, dict) and job.get("source")]
    keep = proposal.get("keep_sources", allowed)
    if not isinstance(keep, list) or any(not isinstance(item, str) for item in keep):
        return None
    named = set(detect_platforms(question))
    required = []
    for job in jobs:
        if any(platform in named for platform in job.get("platforms") or []):
            if job["source"] not in required:
                required.append(job["source"])
    chosen = []
    for source in list(keep) + required:
        if source in allowed and source not in chosen:
            chosen.append(source)
    if not chosen:
        return None
    updated = dict(planned)
    updated["keywords"] = keywords
    updated["jobs"] = []
    for index, job in enumerate(job for job in jobs if job.get("source") in chosen):
        copied = dict(job)
        copied["ordinal"] = index
        copied["keywords"] = keywords
        updated["jobs"].append(copied)
    budget = dict(planned.get("budget") or {})
    budget["keyword_groups"] = len(keywords)
    updated["budget"] = budget
    updated["model_plan"] = True
    return updated


def clamp_ids(cards, limit, proposal):
    """只保留候选里的编号，并且不超过预算。"""
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        return None
    if isinstance(proposal, list):
        raw = proposal
    elif isinstance(proposal, dict):
        raw = proposal.get("ids")
    else:
        return None
    if not isinstance(raw, list):
        return None
    known = [card.get("id") for card in cards if isinstance(card, dict) and card.get("id")]
    chosen = []
    for item in raw:
        if item in known and item not in chosen:
            chosen.append(item)
        if len(chosen) >= limit:
            break
    return chosen or None


def plan(question, platforms=None):
    selected = normalize_platforms(platforms) if platforms else detect_platforms(question)
    task_kind = kind(question)
    jobs = []
    if task_kind == "catalog":
        for source, caps in SOURCE_CAPS.items():
            _add(jobs, source, SOURCE_BY_ID[source]["platforms"][0], caps)
        planned = _number(jobs, question)
        planned["market"] = "both"
        return planned
    if task_kind == "imports":
        for source in IMPORT_SOURCES:
            _add(jobs, source, SOURCE_BY_ID[source]["platforms"][0], ["import"])
        planned = _number(jobs, question)
        planned["market"] = "import"
        return planned
    if task_kind == "read":
        _add(jobs, "Agent-Reach", "网页", ["read"])
        planned = _number(jobs, question)
        planned["market"] = "link"
        return planned
    if task_kind == "compare":
        _add(jobs, "last30days-skill-cn", "中文检索", ["search"])
        _add(jobs, "last30days-skill", "海外检索", ["search"])
        planned = _number(jobs, question)
        planned["market"] = "both"
        return planned
    if task_kind == "hot":
        _add(jobs, "last30days-skill-cn", "热榜", ["hot"])
        planned = _number(jobs, question)
        planned["market"] = "hot"
        return planned
    if task_kind == "public_clue":
        for name in selected or ["小红书"]:
            source = PRIMARY.get(name, "unregistered")
            _add(jobs, source, name, SOURCE_CAPS.get(source, ["search"]))
        _add(jobs, "host-web", "网页", ["search"])
        planned = _number(jobs, question)
        planned["market"] = _market(planned["jobs"])
        return planned
    if not selected:
        _add(jobs, "last30days-skill-cn", "中文检索", ["search"])
    for name in selected:
        source = PRIMARY.get(name)
        if source is None:
            _add(jobs, "unregistered", name, ["search"])
            continue
        caps = ["hot"] if name == "热榜" else SOURCE_CAPS[source]
        if source == "MediaCrawler":
            caps = ["import"]
        _add(jobs, source, name, caps)
    planned = _number(jobs, question)
    planned["market"] = _market(planned["jobs"])
    return planned
