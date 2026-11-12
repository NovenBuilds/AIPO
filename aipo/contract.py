"""来源适配的统一返回。归档时再转换成 save_run 的 bundle。"""

from dataclasses import dataclass


@dataclass
class SourceResult:
    tool: str
    version: str | None
    mode: str
    channels: list
    evidence: list
    raw: object
    raw_name: str
    read_depth: str
    retrieved_at: str | None = None
    registration: str = "回放"

    def as_dict(self):
        return {
            "tool": self.tool,
            "version": self.version,
            "mode": self.mode,
            "channels": self.channels,
            "evidence": self.evidence,
            "read_depth": self.read_depth,
            "retrieved_at": self.retrieved_at,
            "registration": self.registration,
        }


def result(tool, mode, status, platform, path, reason, evidence=None, raw=None, version=None,
           read_depth="", registration=None, raw_name=None):
    if registration is None:
        registration = {"replay": "回放", "live": "实采", "import": "导入"}.get(mode, mode)
    if status in ("timeout", "error", "need_login", "missing_dependency", "blocked", "unknown"):
        if mode != "replay":
            registration = "受阻"
    return SourceResult(
        tool=tool,
        version=version,
        mode=mode,
        channels=[{"platform": platform, "status": status, "path": path, "reason": reason}],
        evidence=list(evidence or []),
        raw=raw if raw is not None else {"status": status, "reason": reason, "mode": mode},
        raw_name=raw_name or (tool.replace("/", "-") + ".json"),
        read_depth=read_depth or reason,
        registration=registration,
    )


def evidence_item(url, platform, title, summary, path, access, published_at=None,
                  date_confidence=None, metrics=None):
    if published_at is None:
        date_confidence = "unknown"
    return {
        "url": url,
        "platform": platform,
        "title": title,
        "summary": summary,
        "published_at": published_at,
        "date_confidence": date_confidence or "unknown",
        "metrics": metrics,
        "path": path,
        "access": access,
    }
