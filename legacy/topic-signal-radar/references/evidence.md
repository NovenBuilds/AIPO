# 成果契约与操作

辅助脚本只做存储，不读取平台、不判断结论。适用于八项工具和宿主补充搜索。`RUN`、输入文件和解释器均使用绝对路径。所有输出默认在项目 `out/`，按北京时间加随机编号隔离，研究结束前不要移动任务目录。

## 原件与短输出

工具支持编排输出时，完整响应接收即落盘，再向分析层回传所需字段；不能控制时如实说明，避免重复打印。搜索先给编号、标题、作者标识、完整来源、日期或未知、必要摘要与互动；访问参数留在原件供详情调用。深读仍看真实正文、关键配图及评论，保留作者与回复关系，摘要不能替代原文，未知字段不补造。

ingest按既有契约复制原件为不可变批次；不要再把归档副本全文回传。inspect结果捕获后只展示必要证据编号、数量、渠道与异常，所选观察按需回读；finalize只回传产物路径与校验结果。原件、完整URL和字段契约保持不变。

## 1. 创建任务

```bash
python3 "$RADAR_ROOT/scripts/save_run.py" init --topic "宋雨琦" --market cn --days 30
```

返回 JSON 字符串即任务路径，绑定为 RUN。market 可为 cn、global、both、hot、link、product、import。init 的日期是研究意图，不会自动过滤证据；热榜/商品快照使用观察时间，不能冒充已验证发布日期。上游实际窗口必须记录在原件并与任务对齐。用户指定历史截止日时传入 `init --as-of YYYY-MM-DD`，并给上游传入相同截止日。

## 2. 原始结果与统一证据

智能体依据上游真实输出生成 bundle JSON（建议放在 RUN 下）。raw_files 相对 bundle 文件位置解析，支持 .json/.jsonl/.csv/.md/.txt/.html，内容必须可解析。拒绝缺失文件和明显凭据文件；该检查不是完整隐私扫描，智能体仍需避免导入含密钥、Cookie 的文件或调试日志。只归档研究内容，不归档上游配置和浏览器会话。

规范示例：

```json
{
  "tool": "last30days-skill-cn",
  "version": "4.0.0-cn",
  "channels": [
    {"platform": "bilibili", "status": "success", "path": "wbi-search", "reason": "实际返回视频搜索结果"},
    {"platform": "xiaohongshu", "status": "need_login", "path": "public-search", "reason": "未取得可用登录入口，公开搜索也无有效结果"}
  ],
  "evidence": [{
    "url": "https://www.bilibili.com/video/BV14Tpq6kExw",
    "platform": "bilibili",
    "title": "【宋雨琦】 ‘Stay’ LIVE CLIP",
    "summary": "标题与搜索摘要；未读取视频或评论正文。",
    "published_at": "2026-10-14",
    "date_confidence": "high",
    "metrics": null,
    "path": "wbi-search",
    "access": "link"
  }],
  "raw_files": ["raw/cn/report.json"]
}
```

示例只是字段说明，不能当作本次采集结果。tool 为八项项目目录名之一或 host-web；version 不知道时用 null。可选 `retrieved_at` 填原件能够证明的采集时间；不知道时省略或 null。脚本另外生成 `archived_at` 归档时间，不能把它冒充采集时间。渠道 status 可为 success、empty、missing_dependency、need_login、blocked、rate_limited、timeout、error、degraded、unknown。`path` 写实际获取路径，不只写目标平台。

access 只能是 link、body、comments、product、monitor_result。published_at 未知用 null 且 date_confidence=unknown；其他可信度为 high/medium/low。metrics 为真实非负数字组成的对象或 null，单项未知也可 null；不补零，不填工具综合评分。价格和商品描述写入 summary 与原件，不混入互动指标。

```bash
python3 "$RADAR_ROOT/scripts/save_run.py" ingest --run "$RUN" --bundle "$BUNDLE"
python3 "$RADAR_ROOT/scripts/save_run.py" inspect --run "$RUN"
```

每次 ingest 写入一个不可变批次，复制原件并记录 SHA-256；验证失败不会产生半个批次。不同工具各交一个批次，失败工具也用空 evidence 与真实渠道状态归档。inspect 返回合并后的证据和稳定的 E 开头编号。

只有“完整 URL 完全一致且平台相同”才合并为一条索引，所有原始观察都保留，指标与时间不互相覆盖。参数、片段不同的链接保守保留，智能体可以指出可能重复但不要擅自删参数。该去重不能自动识别转载、短链或语义重复。

## 3. 简报与信号卡

智能体写 brief.md，重要事实引用 inspect 返回的 `[E…]` 编号及原始链接。脚本会验证编号并自动附实际渠道状态和证据索引；不会验证每句话是否被证据支持，仍需人工/智能体复核。简报至少解释时间、已读深度、主要发现、相反证据或未知项、覆盖缺口。

需求、竞品、商品机会任务可另外写信号卡 JSON 数组：每张卡具有 audience、context、problem、workaround、to_verify 五个非空文字字段，supporting 与 opposing 为证据编号数组。supporting 至少一条，opposing 可以空，但 to_verify 要说明未发现反例不等于没有反例。不将表达兴趣或抱怨直接写成付费意愿。

```bash
python3 "$RADAR_ROOT/scripts/save_run.py" finalize --run "$RUN" --brief "$BRIEF"
# 适用时追加 --cards "$CARDS"
```

定稿输出 `final/run.json`、`final/evidence.json`、`final/report.md` 和可选 `final/signal-cards.json`。已定稿目录不可再次 ingest/finalize；后续研究创建新任务。定稿前可多次添加批次。原件在 batches 下保留，报告不外发、不自动发布。

插件或监控导出首先按原始格式归档，再根据实际字段形成上述 bundle；不要把格式检查通过写成真实平台接通。缺少可定位链接的文件可仅归档原件、空 evidence 并说明缺口。
