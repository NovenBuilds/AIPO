---
name: topic-signal-radar
description: 编排国内外近期讨论研究、热榜、原文补读、评论深挖与商品观察。按任务选择八项本地上游，保留证据和覆盖缺口；需求或竞品任务按需形成信号卡。不用于发帖、私信、交易或管理监控任务。
---

# 话题信号雷达

理解问题，选择必要来源，提取证据并交付中文判断。两个辅助脚本只负责环境检查与归档，研究判断由助手完成。

## 先选路径，再准备

解析本文件软链接后的目录为 `RADAR_ROOT`。已有可用宿主工具或专用服务时，直接检查其当前能力与会话；成功即执行本次查询，不先扫描八项环境或全部插件。安装、连接失败或能力缺失时才读[运行准备](references/runtime.md)，针对所选项目用 `scripts/check_env.py --project <项目名> --json` 辅助诊断。

指定平台任务先读[平台共同规则](references/platform-access.md)，同次任务复用已读规则和授权。来源按目标市场选择；未指定时中文话题先假设中文市场，影响判断才追问，明确海外任务遵从其范围。

| 任务 | 仅加载本次所需说明 |
| --- | --- |
| 小红书逐次查询、正文与评论 | [本机小红书调用卡](references/providers/xiaohongshu-mcp.md)；常规调用不读上游整篇README |
| 中文近期主题、热榜 | [主题研究](references/research.md)中的中文版路线；last30days-skill-cn |
| 海外主题 | 同页海外路线；last30days-skill，保留其必需准备 |
| 国内外对照 | 两路独立执行，保存目录分开；不再经中文版重复桥接 |
| 原文、字幕补读 | [补读说明](references/reading-deep.md#agent-reach)；Agent-Reach |
| 批量笔记、评论取证 | [批量说明](references/reading-deep.md#mediacrawler)；MediaCrawler |
| 用户选定的插件采集 | [社媒助手](references/reading-deep.md#社媒助手)：区分版本与真实能力 |
| 闲鱼查询、既有监控导出 | [商品观察](references/products.md)；goofish-cli / ai-goofish-monitor |

八项是来源池，不是八个串行步骤；完整仓库说明只在相关准备或排障时读取。源码、安装、会话与真实读取是不同状态，历史验收范围见[验证记录](VALIDATION.md)，不据此保证当次成功。

## 材料与交付

按[证据契约](references/evidence.md)建任务、落盘原件并归档。搜索阶段向分析层提供精简列表，选中后读原文、关键配图及评论；避免重复整份展示原始结果。

中文简报包含问题、时间范围、实际来源、发现、反面证据、未知项和下一步；商机任务再形成需求信号卡。保留上游原始输出及其徽标、来源和实际读取深度，跨工具评分不直接比较；平台采样和交付状态以共同规则为准。
