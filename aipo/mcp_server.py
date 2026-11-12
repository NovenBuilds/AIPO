"""stdio 上的 MCP（模型上下文协议）服务。

客户端用换行分隔的 JSON 时按换行回写；客户端用 Content-Length 头时按同样的头回写。
"""

import json
import sys

from aipo import __version__
from aipo.service import Service, ServiceError

PROTOCOL = "2024-11-05"
TOOLS = [
    {
        "name": "start_research",
        "description": "发起研究。传入一句话，返回任务编号和初始状态。相同 request_id 与相同参数复用任务。研究在服务内继续，调用方不需要再调各个平台工具。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "用户的一句话研究问题"},
                "request_id": {"type": "string", "description": "调用方重试编号，可选"},
                "platforms": {"type": "array", "items": {"type": "string"}, "description": "平台范围，可选"},
            },
            "required": ["question"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_research",
        "description": "查看研究状态、各来源进度和阻塞原因。定稿时返回中文报告、证据索引和覆盖情况。",
        "inputSchema": {
            "type": "object",
            "properties": {"research_id": {"type": "string", "description": "任务编号"}},
            "required": ["research_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "resume_research",
        "description": "按原任务编号继续未完成步骤。登录或依赖恢复后传入 answer。已完成批次会保留。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "research_id": {"type": "string", "description": "任务编号"},
                "answer": {"type": "string", "description": "用户补充，例如已登录或跳过"},
            },
            "required": ["research_id"],
            "additionalProperties": False,
        },
    },
]


def read_message(stream):
    while True:
        line = stream.readline()
        if not line:
            return None, None
        if not line.strip():
            continue
        if line.lstrip().startswith(b"{"):
            return json.loads(line.decode("utf-8")), "ndjson"
        headers = [line]
        while True:
            nxt = stream.readline()
            if nxt in (b"\r\n", b"\n", b""):
                break
            headers.append(nxt)
        length = None
        for header in headers:
            if header.lower().startswith(b"content-length:"):
                length = int(header.split(b":", 1)[1].strip())
        if length is None:
            raise ValueError("无法识别的 MCP 帧")
        body = stream.read(length)
        return json.loads(body.decode("utf-8")), "lsp"


def write_message(stream, payload, framing):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if framing == "lsp":
        stream.write(b"Content-Length: %d\r\n\r\n" % len(data))
        stream.write(data)
    else:
        stream.write(data + b"\n")
    stream.flush()


def _arguments(params):
    arguments = (params or {}).get("arguments") or {}
    if isinstance(arguments, str):
        arguments = json.loads(arguments)
    if not isinstance(arguments, dict):
        raise ServiceError("工具参数必须是对象。")
    return arguments


def _text(payload, is_error=False):
    if is_error:
        body = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    else:
        lines = ["任务 %s 状态：%s。" % (payload.get("research_id"), payload.get("status"))]
        if payload.get("phase"):
            lines.append("阶段：%s。" % payload["phase"])
        if payload.get("note"):
            lines.append(payload["note"])
        if payload.get("report_markdown"):
            lines.extend(["", payload["report_markdown"]])
        meta = {key: value for key, value in payload.items() if key != "report_markdown"}
        lines.extend(["", "```json", json.dumps(meta, ensure_ascii=False, indent=2), "```"])
        body = "\n".join(lines)
    return {"content": [{"type": "text", "text": body}], "isError": is_error}


def handle(service, message):
    method = message.get("method")
    params = message.get("params") or {}
    if method == "initialize":
        return {"protocolVersion": params.get("protocolVersion") or PROTOCOL,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "aipo", "version": __version__}}
    if method and method.startswith("notifications/"):
        return None
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": TOOLS}
    if method == "resources/list":
        return {"resources": []}
    if method == "prompts/list":
        return {"prompts": []}
    if method == "tools/call":
        name = params.get("name")
        try:
            arguments = _arguments(params)
            if name == "start_research":
                payload = service.start(arguments.get("question"), arguments.get("request_id"), arguments.get("platforms"))
            elif name == "get_research":
                payload = service.get(arguments.get("research_id"))
            elif name == "resume_research":
                payload = service.resume(arguments.get("research_id"), arguments.get("answer"), sync=False)
            else:
                raise ServiceError("未知工具。")
            return _text(payload)
        except ServiceError as exc:
            return _text("%s" % exc, is_error=True)
    raise ServiceError("不支持的方法。")


def serve(service=None):
    service = service or Service(autostart=True)
    framing = "ndjson"
    while True:
        message, got = read_message(sys.stdin.buffer)
        if message is None:
            break
        framing = got or framing
        if "id" not in message:
            try:
                handle(service, message)
            except ServiceError:
                pass
            continue
        try:
            result = handle(service, message)
            if result is None:
                continue
            write_message(sys.stdout.buffer, {"jsonrpc": "2.0", "id": message["id"], "result": result}, framing)
        except ServiceError as exc:
            write_message(sys.stdout.buffer, {"jsonrpc": "2.0", "id": message["id"], "error": {"code": -32601, "message": str(exc)}}, framing)
        except (ValueError, KeyError, TypeError) as exc:
            write_message(sys.stdout.buffer, {"jsonrpc": "2.0", "id": message["id"], "error": {"code": -32602, "message": type(exc).__name__}}, framing)
    service.close()
    return 0
