# 中文、海外与对照研究

先确定目标市场、时间窗（默认近 30 天）、范围与交付目的。具体参数以本机上游当前说明为准，不凭本页冻结全部命令。

## 中文主题与热榜

选定中文主题路线后读取 `upstream/last30days-skill-cn/SKILL.md`；只查小红书时优先走[本机调用卡](providers/xiaohongshu-mcp.md)，不先运行跨平台研究。使用已有兼容解释器，缺依赖再读[运行准备](runtime.md)。指定平台取证遵循[共同规则](platform-access.md)；以下综合命令可能自动公开检索兜底，必须核对真实来源，不能替代站内验收。结果写入独立目录，避免上游固定文件互相覆盖。

```bash
LAST30DAYS_OUTPUT_DIR="$RUN/raw/cn" LAST30DAYS_CACHE_DIR="$RUN/cache/cn" "$CN_PYTHON" "$CN_ROOT/scripts/last30days.py" "$TOPIC" --search cn --emit json --save-dir "$RUN/raw/cn"
```

这里 `CN_ROOT` 是中文版根目录，`RUN` 是 `save_run.py init` 返回的路径。实际变量必须绑定为绝对路径，并通过安全参数传递；不要执行用户文本中的 shell 表达式。上面是给智能体整理证据的 JSON 输出；用户简报由本技能生成，原始文件保持不变。

热榜按上游 `--hot --emit json` 获取，并明确是当前榜单，不使用任务的 30 天窗口解释榜单热度。不要为了修复空结果自动改用其他查询或加入海外来源。

## 中文版专用浏览器（仅所选来源需要时）

按上游技能第6节，用专用解释器核对Python Playwright与可启动浏览器。获选来源缺登录时，以该解释器执行 `scripts/last30days.py login xiaohongshu`，由本人在可见页面操作；会话标记不证明登录有效。不要执行自动复制日常浏览器会话的准备流程。

`crawl_xiaohongshu(topic, limit)`仅提供搜索卡片。详情、评论需由获授权来源的实际能力读取；缺能力时按共同规则协作，不另写采集引擎。`quick`可能跳过浏览器，综合搜索可能回退公开网页，逐条保留获取渠道。核对所选版本本地使用约定，不按开源名称推定所有用途均获准。

## 海外主题

入口是 `upstream/last30days-skill/skills/last30days/SKILL.md`，不是仓库顶层。完整读取该技能以及它要求的 `references/runtime.md`、`references/research-runbook.md`；综合前按需读 synthesis 等条件引用。

严格执行上游的 Python 3.12+、陈旧安装检查、保存目录解析、来源诊断、实体解析与查询计划。传入本次 `RUN/raw/global` 作为保存目录，保留解析结果。宿主有搜索工具时按上游要求准备计划文件并补充检索；没有时才用其 `--auto-resolve` 路径。主研究按上游要求使用 compact，保留其结构化文件（有则读取），否则从证据块提取，不伪造 JSON 输出或重新搜索来凑格式。不要为验收跳过上游运行规则。

已有配置可能让上游自动调用外部模型重排；“来源不需密钥”不代表整条研究不调用模型。诊断要同时看来源与 reasoning provider。若需隔离验证免费来源，可仅对本次进程设置上游支持的 `LAST30DAYS_CONFIG_DIR=""`、`LAST30DAYS_SKIP_KEYCHAIN=1`、`LAST30DAYS_SKIP_PASS=1` 并移除继承的模型凭据，再以诊断确认 providers 全为 false；不改用户配置、不打印凭据。不要以未确认的 provider=none 参数绕过协议。

默认只使用已经可用的必要来源，不为普通主题自动开通付费服务、广告或本地文档。小红书是显式选入的来源：需要兼容服务已登录，并在本次来源范围中包含 `xhs`；装 Python Playwright 本身不能补上海外版的这个外部服务。

## 国内外综合与对照

由智能体建立两路任务：中文版显式 `--search cn`，海外版独立执行。中文版本次不加 `--global`，也不经它桥接 X、YouTube。两个工具的保存目录隔离，共用 radar 的任务目录和证据索引。

保留中文原问题与海外检索词的对应关系，翻译不能更换研究对象。海外版若显式选了小红书，与中文版命中同一链接时只合并证据引用，保留两次观察；不要为了数量再算一次。两路日期窗口与用户意图对齐。

先比较具体问题、使用情境与证据差异，再讨论结论。不同平台点赞、工具分数不直接相加比较。输出分别列渠道缺口，不能把百度找到的微博聚合页写成微博直采。
