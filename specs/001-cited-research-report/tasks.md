# Tasks: 带引用的商机研究报告

**Input**: Design documents from `/specs/001-cited-research-report/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: 规格要求可独立验证，任务包含回归测试。

**Organization**: 按用户故事分组。现有服务已经能回放，任务只补缺口。

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup

**Purpose**: 确认规格位置，不新建第二套服务。

- [x] T001 确认规格目录 `specs/001-cited-research-report/` 与 `.specify/feature.json` 指向同一功能

## Phase 2: Foundational

**Purpose**: 模型提案的收紧规则，供后续故事使用。

- [x] T002 在 `aipo/planner.py` 收紧关键词和来源：最多 3 个关键词、每个不超过 40 字、不能新增来源、不能删除用户点名平台
- [x] T003 在 `aipo/planner.py` 收紧深读编号：只能选候选内的编号，小红书上限 6、闲鱼上限 5

## Phase 3: User Story 1 - 一句话得到有出处的报告 (Priority: P1)

**Goal**: 已配置模型时规划、选择深读并写出带引用判断；失败时回到程序简报。

**Independent Test**: 本地兼容接口返回独特关键词、指定笔记和带编号判断；未配置模型的回放报告保持程序简报。

- [x] T004 [US1] 在 `aipo/model.py` 增加规划、深读和判断三次调用，判断必须引用给定编号且不得写登记
- [x] T005 [US1] 在 `aipo/runner.py` 于首次执行时采用收紧后的计划，并把合法的完整判断替换机会判断到最小付费验证之间的段落
- [x] T006 [US1] 在 `aipo/live.py` 让小红书只深读被选中的、带令牌的笔记，未选中的保留搜索卡片
- [x] T007 [US1] 在 `tests/test_aipo.py` 用本地模型接口和本地小红书接口验证关键词、深读篇数和引用

## Phase 4: User Story 2 - 小红书、闲鱼和其他来源 (Priority: P2)

**Goal**: 闲鱼搜索后读取详情；其他来源继续按已有能力记录，不把缺失写成成功。

**Independent Test**: 假的闲鱼命令只对选中商品调用详情；诊断和指纹单独记录真实环境。

- [x] T008 [US2] 在 `aipo/live.py` 用 `auth status --format json` 确认登录，只归档是否有效
- [x] T009 [US2] 在 `aipo/live.py` 对选中的数字商品编号调用 `item get`，搜索卡片和详情分开计算读取深度
- [x] T010 [US2] 在 `docs/验收/阶段检查点.md` 按来源记下版本、读取深度、证据和阻塞，回放与实采分开

## Phase 5: User Story 3 - 中断、部分失败和价格边界 (Priority: P3)

**Goal**: 重启恢复和部分失败保持可用，报告分开挂牌价与成交证据。

**Independent Test**: 现有重启和超时测试继续通过；只有挂牌价时报告写明没有独立核验成交。

- [x] T011 [US3] 在 `aipo/report.py` 分开挂牌价、卖家自述、平台公开标记和独立核验成交
- [x] T012 [US3] 在 `aipo/live.py` 把闲鱼 `price` 写成挂牌价，把已售状态写成平台公开标记，把描述写成卖家自述
- [x] T013 [US3] 在 `tests/test_aipo.py` 验证详情调用、平台状态和“没有独立核验成交”
- [x] T014 [US3] 保持 `tests/test_aipo.py` 中的重启恢复和部分来源超时断言通过

## Phase 6: Polish

- [x] T015 更新 `docs/模型配置.md` 和 `docs/验收/样例报告-小程序回放.md`，使说明与实际报告一致
- [x] T016 运行 `tests/test_aipo.py` 和 `legacy/topic-signal-radar/tests`，把结果写入 `docs/验收/阶段检查点.md`

## Dependencies

1. T001 后做 T002、T003。
2. T002 和 T003 完成后做 T004、T005、T006、T007。
3. T008、T009 可在 T003 之后与用户故事 1 并行，但测试 T013 依赖它们。
4. T011、T012 完成后做 T013。
5. T014、T015、T016 在实现之后。

## Parallel example

T008 与 T011 修改不同段落，可先后落地到 `aipo/live.py` 和 `aipo/report.py`。T004 与 T011 也在不同文件。

## Implementation strategy

先保住回放报告，再让模型管线在配置存在时替换判断。闲鱼详情和价格分类用可重复的假命令验收。真实小红书、闲鱼和模型密钥缺失时只记录阻塞，不改登记。

## Blocked on external input

这些任务没有可继续写的代码。缺的是运行环境输入。不要把回放或本地桩记成完成。

- [ ] T017 配置 `AIPO_MODEL_BASE_URL`、`AIPO_MODEL_NAME` 和 `AIPO_MODEL_API_KEY` 后，用真实模型对同一句话重跑 `start_research`
- [ ] T018 在已登录的小红书服务上复验搜索、正文和评论，并记下当次版本与读取深度
- [ ] T019 提供闲鱼登录后复验 `auth status`、`search items` 和 `item get` 的原生字段
- [ ] T020 放上中文检索、海外检索和 Agent-Reach 的已安装副本后，按渠道重跑搜索或补读
- [ ] T021 提供社媒助手、闲鱼监控或获准的 MediaCrawler 导出文件后，再验导入；仍然不启动爬虫
