"""由证据生成中文简报。引用编号必须来自归档，模型文字不能替换这层校验。"""

import re

SUPPORT = ("想找", "求推荐", "愿意付", "太耗时", "有没有人做")
OPPOSE = ("已经用", "解决了", "不需要", "免费就", "不必", "自己做了")
HOURS_RE = re.compile(r"(\d+)\s*小时")
PRICE_RE = re.compile(r"挂牌价\s*([0-9]+(?:\.[0-9]+)?)")
ACCESS_RANK = {"comments": 5, "body": 4, "product": 3, "monitor_result": 3, "link": 1}


def _best(evidence):
    return max(evidence["observations"], key=lambda item: (ACCESS_RANK.get(item.get("access"), 0), item.get("archived_at") or ""))


def _views(aggregate):
    views = []
    for item in aggregate.get("evidence") or []:
        obs = _best(item)
        views.append({
            "id": item["id"],
            "url": item["url"],
            "platform": item["platform"],
            "title": obs.get("title") or "",
            "summary": obs.get("summary") or "",
            "access": obs.get("access") or "link",
            "path": obs.get("path") or "",
            "published_at": obs.get("published_at"),
            "tool": obs.get("tool"),
        })
    return views


def _role(view):
    text = view["title"] + view["summary"]
    if view["access"] in ("product", "monitor_result"):
        return "product"
    if any(word in text for word in OPPOSE):
        return "opposing"
    if any(word in text for word in SUPPORT) or view["access"] in ("body", "comments"):
        if any(word in text for word in OPPOSE):
            return "opposing"
        if any(word in text for word in SUPPORT) or view["access"] == "comments":
            return "supporting" if any(word in text for word in SUPPORT) or "评论" in view["title"] else "discussion"
        return "discussion"
    return "context"


def _site(path):
    if "public-index" in path or "public-clue" in path:
        return "公开索引"
    if "hot-snapshot" in path:
        return "热榜快照"
    if "/import" in path:
        return "导入"
    if "in-site" in path:
        return "站内"
    return "未分类"


def registration_of(sources):
    live = [item for item in sources if item.get("mode") == "live" and item.get("status") in ("success", "empty", "degraded")]
    if live:
        return "实采"
    modes = {item.get("mode") for item in sources if item.get("status") != "pending"}
    if modes and modes <= {"import"}:
        return "导入"
    if "replay" in modes:
        return "回放"
    return "受阻"


def _cite(view):
    return "[%s]" % view["id"]


def build_brief(question, aggregate, sources, plan, mode):
    views = _views(aggregate)
    by_role = {"supporting": [], "opposing": [], "discussion": [], "product": [], "context": []}
    for view in views:
        role = _role(view)
        if role == "supporting" and view["access"] == "link" and "想找" not in view["summary"] and "太耗时" not in view["summary"]:
            role = "context"
        by_role.setdefault(role, []).append(view)
    hours = HOURS_RE.search(question or "")
    hours_text = hours.group(1) if hours else None
    reg = registration_of(sources)
    lines = ["# 商机研究简报", ""]
    if reg == "实采":
        lines.append("登记：实采。下面只把真实返回的来源算作实采，失败来源单独列出。")
    elif reg == "导入":
        lines.append("登记：导入。本任务没有实采结果。导入不等于站内实采。")
    elif reg == "回放":
        lines.append("登记：回放。本任务没有实采结果。")
    else:
        lines.append("登记：受阻。本任务没有实采结果。")
    lines += ["", "## 研究问题", "", (question or "").replace("[", "［"), ""]
    lines += ["## 实际使用的来源与覆盖", ""]
    lines.append("执行模式：%s。归档里的 market 只是旧枚举的近似值，覆盖以本节为准。" % ("回放" if mode == "replay" else "实采或导入"))
    if mode == "replay":
        lines.append("计划关键词只来自问题文本，不代表回放夹具是这些词的检索结果。关键词：%s。" % "、".join(plan.get("keywords") or []))
    else:
        lines.append("计划关键词：%s。每个来源只搜索一次。" % "、".join(plan.get("keywords") or []))
    budget = plan.get("budget") or {}
    lines.append("采样预算：最多 %s 篇、深读 %s 篇、每篇评论索引 %s 条、商品 %s 条。实际条数见各来源，不用预算冒充已读数量。" % (
        budget.get("max_notes", 30), budget.get("max_deep_reads", 6), budget.get("max_comments_per_note", 20), budget.get("max_products", 5)))
    if not sources:
        lines.append("- 没有来源记录。")
    mode_label = {"replay": "回放", "live": "实采", "import": "导入"}
    for source in sources:
        lines.append("- %s / %s：状态 %s；登记 %s；读取 %s；路径 %s；%s" % (
            source.get("source"), "、".join(source.get("platforms") or []), source.get("status"),
            mode_label.get(source.get("mode"), source.get("mode")), source.get("read_depth") or "未记录",
            source.get("path") or "无", source.get("reason") or ""))
    lines.append("观察时间：夹具和未知原件都不编造采集时间。归档时间由归档程序写入，不能当成平台上的发布时间。")
    lines += ["", "## 机会判断", ""]
    if by_role["supporting"] or by_role["discussion"]:
        focus = (by_role["supporting"] or by_role["discussion"])[0]
        if "门店" in focus["summary"] or "门店" in focus["title"] or any("门店" in item["summary"] for item in views):
            lines.append("建议只试一个方向：给需要合并多家门店表格的人，做一个一次性汇总的小工具。样本只有这一条线索，不并列三个方向。")
        else:
            lines.append("建议只围绕已读到的一条需求做最小试验：%s %s" % (focus["title"], _cite(focus)))
        if "微信小程序" in (question or ""):
            lines.append("供给能力来自题目而不是平台证据：会开发微信小程序。")
        if hours_text:
            lines.append("时间约束来自题目：每周约 %s 小时。" % hours_text)
    else:
        lines.append("还不能提出值得收费的方向。证据不足，或来源没有返回可用样本。")
    lines += ["", "## 目标客户", ""]
    if any("门店" in (view["title"] + view["summary"]) for view in views):
        anchor = next(view for view in views if "门店" in (view["title"] + view["summary"]))
        lines.append("目标客户暂定为需要手工合并多个门店表格的经营者。依据是已读材料里的使用者描述 %s，不是人口统计。" % _cite(anchor))
    elif views:
        lines.append("目标客户还不具体：只能暂时记为留下这些话的人 %s。身份、行业和预算都没有写清。" % _cite(views[0]))
    else:
        lines.append("没有样本，不能指定目标客户。")
    lines += ["", "## 支持证据", ""]
    if by_role["supporting"] or by_role["discussion"]:
        for view in (by_role["supporting"] + by_role["discussion"]):
            lines.append("- %s %s：%s" % (_cite(view), view["title"], view["summary"]))
        lines.append("这些话说明有人感到麻烦或在找人做事，没有写明已经付款。")
    else:
        lines.append("没有读到可支撑付费方向的讨论或评论。")
    lines += ["", "## 反例", ""]
    if by_role["opposing"]:
        for view in by_role["opposing"]:
            lines.append("- %s %s：%s" % (_cite(view), view["title"], view["summary"]))
        lines.append("反例是替代办法或反对意见，会缩小愿意付费的范围。")
    else:
        lines.append("没有读到明确反例。没有读到反例，不等于没有反例。")
    lines += ["", "## 交叉证据", ""]
    discussions = [view for view in views if view["access"] in ("body", "comments", "link")]
    products = by_role["product"]
    if discussions and products:
        lines.append("材料类型分开记录：讨论正文、评论和商品供给。讨论与商品可以放在一起看，但不能合成一个成交故事。")
        lines.append("讨论侧：%s。" % "、".join(_cite(view) for view in discussions[:4]))
        lines.append("供给侧：%s。" % "、".join("%s %s" % (_cite(view), view["title"]) for view in products))
        lines.append("两侧都没有核验成交、复购或净利润。")
    else:
        lines.append("目前没有可交叉的讨论和商品两侧样本。缺的一侧保持为结论缺口。")
    lines += ["", "## 价格与成本假设", ""]
    prices = []
    for view in views:
        for match in PRICE_RE.finditer(view["summary"]):
            prices.append((match.group(1), view))
    if prices:
        for amount, view in prices:
            lines.append("- 看到挂牌价 %s，出处 %s。这是挂牌或咨询标价，不是成交价，也不能当成买家愿付价格。" % (amount, _cite(view)))
    else:
        lines.append("证据里没有挂牌价或费用数字，这里不编价格。")
    if hours_text:
        lines.append("交付工时假设：每周 %s 小时，来自题目。若两周内做不出可交付的一版，就超出这个约束。" % hours_text)
    else:
        lines.append("交付工时未知，题目没有给出每周可投入时间。")
    lines.append("获客成本未知。运行成本和售后成本也未知。")
    lines += ["", "## 最小付费验证", ""]
    if by_role["supporting"] or (by_role["discussion"] and products):
        hour_part = "每周不超过 %s 小时" % hours_text if hours_text else "在题目没有写明的时间里先控制范围"
        lines.append("用%s，两周内只做能演示核心步骤的一版。向 3 位符合上面描述的人报价，要求先付款再交付。" % hour_part)
        lines.append("停止条件：两周内没有人支付，或对方说明已有免费替代并拒绝付费。口头说想要但不付款，视为未通过。")
    else:
        lines.append("现在不要开发。最小动作是补样本，而不是做产品。")
        lines.append("停止条件：仍然只有空结果、一条摘要或失败来源时，结束这个方向。至少需要 5 条独立需求原话，外加一个可核对的价格信号，才进入收费试验。")
    lines += ["", "## 结论缺口", ""]
    if not views:
        lines.append("- 证据不足：没有可引用的原始材料。")
    if any(source.get("status") == "empty" for source in sources):
        lines.append("- 至少有一个来源是空结果。空结果是结果，不是尚未查询。")
    if any(source.get("status") == "timeout" for source in sources):
        lines.append("- 有来源超时，对应的平台不能补进结论。")
    if any(source.get("status") in ("need_login", "missing_dependency", "error", "blocked") for source in sources):
        lines.append("- 有来源受阻。受阻原因见来源列表，不能用别的平台样本假装补齐。")
    if any(view["access"] == "link" for view in views) and not any(view["access"] in ("body", "comments") for view in views):
        lines.append("- 证据不足：只有链接或摘要，没有正文和评论。")
    unknown_dates = sum(1 for view in views if not view["published_at"])
    if views:
        lines.append("- %s 条材料的发布时间未知。" % unknown_dates)
    lines.append("- 成交、复购、净利润和获客成本都没有核验。")
    if reg != "实采":
        lines.append("- 本次登记不是实采，不能写成平台上已经验证过的需求。")
    public = [view for view in views if _site(view["path"]) == "公开索引" or _site(view["path"]) == "热榜快照"]
    insite = [view for view in views if _site(view["path"]) == "站内"]
    if public:
        lines.append("- 公开索引或榜单 %s 条，不能写成站内讨论。" % len(public))
    if any("public-clue" in view["path"] for view in views):
        lines.append("- 公开线索不能代替站内样本。")
    if insite:
        lines.append("- 站内材料 %s 条，路径里带 in-site。" % len(insite))
    lines += ["", "## 证据一览", ""]
    if not views:
        lines.append("没有证据编号。")
    for view in views:
        lines.append("- %s（%s / %s / %s）%s" % (_cite(view), view["platform"], _site(view["path"]), view["access"], view["title"]))
    brief = "\n".join(lines).rstrip() + "\n"
    cards = None
    supporting_ids = [view["id"] for view in by_role["supporting"]] or [view["id"] for view in by_role["discussion"] if view["access"] in ("body", "comments")]
    if supporting_ids:
        audience = "需要手工合并多个门店表格的经营者" if any("门店" in (view["summary"] + view["title"]) for view in views) else "留下这条需求、但身份尚未核清的人"
        cards = [{
            "audience": audience,
            "context": "题目与已读材料限定的一次小范围试验",
            "problem": (by_role["supporting"] or by_role["discussion"])[0]["title"][:80] or "已读到的问题",
            "workaround": by_role["opposing"][0]["title"][:80] if by_role["opposing"] else "已读材料里还没有替代办法",
            "supporting": supporting_ids[:4],
            "opposing": [view["id"] for view in by_role["opposing"][:4]],
            "to_verify": "未发现更多反例不等于没有反例。成交价、付费意愿和获客成本都还没有证实。",
        }]
    return brief, cards


def coverage(sources, aggregate):
    views = _views(aggregate) if aggregate else []
    return {
        "registration": registration_of(sources),
        "live_success_count": sum(1 for item in sources if item.get("mode") == "live" and item.get("status") in ("success", "empty", "degraded")),
        "replay_count": sum(1 for item in sources if item.get("mode") == "replay"),
        "import_count": sum(1 for item in sources if item.get("mode") == "import"),
        "public_index_ids": [view["id"] for view in views if _site(view["path"]) in ("公开索引", "热榜快照")],
        "in_site_ids": [view["id"] for view in views if _site(view["path"]) == "站内"],
        "evidence_ids": [view["id"] for view in views],
    }
