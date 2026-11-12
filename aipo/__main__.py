"""命令行入口。日常研究走 MCP；这里用于启动、同步验收和诊断。"""

import argparse
import json
import sys

from aipo.config import ConfigError, load_config
from aipo.fingerprints import compare_local, render_local
from aipo.mcp_server import serve
from aipo.registry import render_matrix_md
from aipo.service import Service, ServiceError


def _service():
    return Service(load_config(), autostart=False)


def main(argv=None):
    parser = argparse.ArgumentParser(description="AIPO 商机研究服务")
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("serve")
    start = sub.add_parser("start")
    start.add_argument("--question", required=True)
    start.add_argument("--request-id")
    start.add_argument("--platform", action="append")
    start.add_argument("--sync", action="store_true")
    get = sub.add_parser("get")
    get.add_argument("--id", required=True)
    resume = sub.add_parser("resume")
    resume.add_argument("--id", required=True)
    resume.add_argument("--answer")
    resume.add_argument("--sync", action="store_true")
    sub.add_parser("fingerprint")
    doctor = sub.add_parser("doctor")
    doctor.add_argument("--probe", action="store_true")
    sub.add_parser("map")
    args = parser.parse_args(argv)
    try:
        if args.action == "serve":
            return serve()
        if args.action == "map":
            print(render_matrix_md())
            return 0
        if args.action == "fingerprint":
            print(json.dumps(compare_local(load_config()), ensure_ascii=False, indent=2))
            return 0
        if args.action == "doctor":
            return doctor(args.probe)
        service = _service()
        if args.action == "start":
            payload = service.start(args.question, args.request_id, args.platform)
            if args.sync and not payload.get("reused"):
                service.run(payload["research_id"])
                payload = service.get(payload["research_id"])
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        elif args.action == "get":
            print(json.dumps(service.get(args.id), ensure_ascii=False, indent=2))
        else:
            print(json.dumps(service.resume(args.id, args.answer, sync=args.sync), ensure_ascii=False, indent=2))
    except (ServiceError, ConfigError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


def doctor(probe):
    from aipo.archive import check_env
    config = load_config()
    print(render_local(compare_local(config)))
    module = check_env()
    selected = list(config.check_env_projects()) or None
    report = module.inspect(config.check_env_projects(), probe=probe, selected=selected)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
