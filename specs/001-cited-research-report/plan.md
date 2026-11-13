# Implementation Plan: 带引用的商机研究报告

**Branch**: `cursor/remaining-acceptance-94b4` | **Date**: 2026-11-13 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-cited-research-report/spec.md`

## Summary

在已经落地的研究服务上补齐三件事：已配置模型时由模型规划关键词和来源、选择深读样本、写出带引用的中文判断；闲鱼在搜索后读取详情，并把挂牌价、卖家自述、平台状态和独立核验成交分开；验收记录继续区分回放、导入和实采。程序保留预算、来源白名单、引用校验和重启恢复。

## Technical Context

**Language/Version**: Python 3.12，沿用仓库现有标准库实现

**Primary Dependencies**: 现有 `aipo` 包、旧归档程序 `legacy/topic-signal-radar/scripts/save_run.py`、已登记上游命令或本地服务。模型使用已有的 OpenAI 兼容聊天接口，不新增供应商。

**Storage**: SQLite 任务库；原始材料和报告沿用归档目录

**Testing**: `unittest`。服务测试 `tests/test_aipo.py`，迁入基线 `legacy/topic-signal-radar/tests`

**Target Platform**: 本机常驻进程，标准输入输出上的研究入口

**Performance Goals**: 沿用现有来源超时和采样预算，不新增吞吐指标

**Constraints**: 不提交上游源码、密钥或平台会话。回放不得填实采。用户点名的平台不能被模型删掉。深读不超过现有预算。

**Scale/Scope**: 一次研究、九类已登记来源、每个来源一次搜索。首个完整问题仍是每周 5 小时的微信小程序方向，优先看小红书和闲鱼。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- 一个入口：不新增对外工具。通过。
- 复用已登记来源：模型只能在程序选出的来源里取舍。通过。
- 回放不是实采：深读选择只影响实采；回放夹具保持原样。通过。
- 程序守边界：预算、超时、编号和引用校验仍由程序执行。通过。
- 证据可回读：不改证据编号算法，不重写已完成批次。通过。

Phase 1 之后复检：合同只描述现有三个工具和模型 JSON 形状，没有新的对外产品入口。通过。

## Project Structure

### Documentation (this feature)

```text
specs/001-cited-research-report/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── research-tools.md
│   └── model-json.md
└── tasks.md
```

### Source Code (repository root)

```text
aipo/
├── model.py          # 模型规划、深读选择、判断
├── planner.py        # 收紧模型提案
├── runner.py         # 把模型接进取证和定稿
├── live.py           # 小红书深读选择、闲鱼详情和价格分类
├── report.py         # 挂牌、平台标记、卖家自述、成交分开
└── service.py        # 测试可注入的规划与选择函数

tests/test_aipo.py
docs/模型配置.md
docs/验收/阶段检查点.md
docs/验收/样例报告-小程序回放.md
```

## Complexity Tracking

没有违反章程的额外复杂度。模型失败时回到已经存在的程序简报。
