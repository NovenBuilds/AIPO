"""从一句话里识别验收与规划用的任务类型。

这些词只影响回放夹具和来源选择。实采模式不会用夹具填结果。
"""

import re

URL_RE = re.compile(r"https?://[^\s\]\)】》>，。；、]+")


def kind(question):
    text = question or ""
    if "全来源回放" in text:
        return "catalog"
    if "会话失效" in text or "登录失效" in text:
        return "session_invalid"
    if "超时" in text:
        return "partial_timeout"
    if "空结果" in text:
        return "empty"
    if "证据不足" in text:
        return "insufficient"
    if "公开线索" in text or "公开网页" in text:
        return "public_clue"
    if "热榜" in text:
        return "hot"
    if "导入" in text:
        return "imports"
    if "补读" in text or URL_RE.search(text):
        return "read"
    if "国内外" in text or "对照" in text:
        return "compare"
    if "指定" in text or "只看" in text:
        return "specified"
    return "primary"


def urls(question):
    return URL_RE.findall(question or "")


def intent(question):
    text = question or ""
    if any(word in text for word in ("评估", "这个想法", "值不值得做")):
        return "评估已有想法"
    if any(word in text for word in ("指定", "只看", "研究这个平台", "研究某个平台")):
        return "研究指定平台"
    return "找新项目"
