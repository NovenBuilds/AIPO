# topic-signal-radar：话题信号雷达

本地智能体的研究编排技能，按任务取近期讨论、补读原文、深挖评论或观察商品。研究由助手完成；两个辅助脚本分别做环境检查、证据留存，不另建模型或采集服务。

## 常规使用

直接描述目标，例如“研究独立开发者最近愿意付费解决的问题”“补读这条笔记的评论”“查询一个闲鱼品类”。从[技能入口](SKILL.md)选必要路线。

已有宿主工具或专用服务时，先验证该来源和会话，成功就查询；失败或缺少能力后再扩展入口发现和环境诊断。小红书常规调用读[短调用卡](references/providers/xiaohongshu-mcp.md)，安装、升级或协议排障时才读上游整篇说明。

平台接入、授权、采样、停止条件及交付状态统一维护在[平台共同规则](references/platform-access.md)。实际验收范围见[验证记录](VALIDATION.md)，历史成功不保证本轮会话有效。

## 八项按需来源

| 项目 | 用途 | 说明入口 |
| --- | --- | --- |
| last30days-skill | 海外近期研究 | [主题研究](references/research.md) |
| last30days-skill-cn | 中文研究、热榜 | 同上；国内外对照两路独立执行 |
| Agent-Reach | 原文、字幕补读 | [补读与评论](references/reading-deep.md) |
| MediaCrawler | 批量笔记、评论取证 | 同上；核对实际数量限制 |
| xiaohongshu-mcp | 本机小红书逐次读取 | [短调用卡](references/providers/xiaohongshu-mcp.md) |
| social-media-copilot | 选定版本的插件或导出 | [社媒助手](references/reading-deep.md#社媒助手) |
| goofish-cli | 闲鱼商品查询 | [商品观察](references/products.md) |
| ai-goofish-monitor | 既有监控导出分析 | 同上；不接管账号或任务 |

这些是可选来源，不要求装齐或同时运行。源码与获取方式见[上游清单](upstream/README.md)，不等同于部署状态。

## 文件与准备

共享入口 `~/.agents/skills/topic-signal-radar` 指向本目录；引用按解析后的实际目录定位。依赖、连接或安装问题再读[运行准备](references/runtime.md)，仅检查相关项目，不覆盖已有源码和环境。

按[证据契约](references/evidence.md)保存完整原件、统一证据及中文简报。输出默认在被忽略的 `out/<任务编号>/`。向分析层先给必要字段，深读时看真实原文；归档检查返回数量、引用和异常摘要，避免重复打印整份原件。

## 验证与维护

```bash
python3 -m unittest discover -s tests -v
```

离线测试覆盖环境状态、证据与归档行为，不证明真实平台接通。上游不随父仓库提交，ZIP副本提交未知；本地适配见[补丁记录](patches/README.md)，更新前保留既有差异。
