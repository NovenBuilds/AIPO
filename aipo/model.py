"""可选的 OpenAI 兼容模型。未配置时研究仍由程序完成。"""

import json
import re
import urllib.request

CITE_RE = re.compile(r"\[(E[a-f0-9]{16})\]")


def complete(config, system, user):
    if not config.model_enabled():
        return None
    url = config.model_base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": config.model_name,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers={
        "Content-Type": "application/json",
        "Authorization": "Bearer " + config.model_api_key(),
    })
    with urllib.request.urlopen(request, timeout=config.model_timeout) as response:
        body = json.loads(response.read(1024 * 1024).decode("utf-8"))
    return body["choices"][0]["message"]["content"]


def _parse_object(text):
    if not text:
        return None
    raw = text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _ask_json(config, system, user):
    try:
        return _parse_object(complete(config, system, user))
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None


def propose_plan(config, question, planned):
    sources = [job["source"] for job in planned.get("jobs") or []]
    system = (
        "你是研究规划器。只输出一个 JSON 对象，不要写解释。"
        "只能使用给定来源编号调整关键词，不能新增来源，不能要求实采或编造成交。"
        "关键词最多 3 个，每个不超过 40 个字。"
        '格式：{"keywords":["..."],"keep_sources":["来源编号"]}'
    )
    user = "问题：%s\n已选来源：%s\n程序关键词：%s" % (
        question, "、".join(sources), "、".join(planned.get("keywords") or []))
    return _ask_json(config, system, user)


def propose_selection(config, question, cards, limit):
    system = (
        "你只输出 JSON 对象，从候选里选出最值得深读的 id，最多 %s 个。"
        "只能使用给定 id。不要编造。格式：{\"ids\":[\"...\"]}" % limit
    )
    lines = ["问题：%s" % question, "候选："]
    for card in cards:
        lines.append("- %s | %s" % (card.get("id"), str(card.get("title") or "")[:80]))
    return _ask_json(config, system, "\n".join(lines))


def propose_report(config, question, evidence_ids, evidence_lines):
    """返回模型判断原文。引用是否合法由调用方检查。"""
    system = (
        "根据给定证据写中文商机判断，用来替换程序简报里从机会判断到最小付费验证的段落。"
        "必须包含这些字：目标客户、反例、挂牌、成交、最小付费验证、停止条件。"
        "每个事实句使用给定的 [E…] 编号。不要写登记二字。不要编造证据和问题里没有的数字。"
        "挂牌价不是成交价。没有独立核验成交时要写明没有成交证据。不要声称实采成功。"
    )
    user = "问题：%s\n可用编号：%s\n材料：\n%s" % (question, "、".join(evidence_ids), "\n".join(evidence_lines))
    try:
        text = complete(config, system, user)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None
    return text


def supplement(config, question, evidence_ids, evidence_lines):
    """返回可附加的模型段落；引用不合法时返回 None。"""
    if not config.model_enabled():
        return None
    system = "你只能根据给定证据写一段中文判断。每个事实句都要带给定的 [E…] 编号。不要声称实采，不要编造价格或成交。"
    user = "问题：%s\n可用编号：%s\n材料：\n%s" % (question, "、".join(evidence_ids), "\n".join(evidence_lines))
    try:
        text = complete(config, system, user)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None
    if not text or "登记：实采" in text or "实采成功" in text:
        return None
    cited = set(CITE_RE.findall(text))
    if not cited or not cited <= set(evidence_ids):
        return None
    return text.strip()
