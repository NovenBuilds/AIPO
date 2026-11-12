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
