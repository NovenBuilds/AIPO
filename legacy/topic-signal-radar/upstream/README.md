# 本地上游项目

本目录保存 topic-signal-radar（话题信号雷达）调研使用的上游源码，包括 Git 克隆和 ZIP 解压副本。项目源码由根目录 `.gitignore` 按实际目录名忽略，本说明保留在 `evolution_lab` 中。

当前八项依据用户提供的资料与本地目录、上游自带说明整理；源码信息沿用2026-10-24核对结果，目录及接入范围于2026-11-03更新。这里记录的是项目定位与源码状态，不代表已完成安装、登录配置或实际采集验证。

## 八个项目与本机目录

| 项目 / 上游地址 | 本机目录 | 获取方式 / 本机版本 | 形态 |
|---|---|---|---|
| [last30days-skill](https://github.com/mvanhorn/last30days-skill) | `last30days-skill/` | Git 克隆，提交 `f3cd06a` | 智能体技能（Agent Skill）＋命令行工具（CLI） |
| [last30days-skill-cn](https://github.com/Jesseovo/last30days-skill-cn) | `last30days-skill-cn/` | Git 克隆，提交 `af785c6` | 智能体技能＋命令行工具，中文衍生版 |
| [Agent-Reach](https://github.com/Panniantong/Agent-Reach) | `Agent-Reach/` | Git 克隆，提交 `beabda7` | 命令行工具 / 面向智能体的多渠道读网工具 |
| [social-media-copilot](https://github.com/iszhouhua/social-media-copilot) | `social-media-copilot/` | ZIP 解压副本，无 `.git` | 浏览器插件；另有提供应用程序接口（API）的服务端分支 |
| [xiaohongshu-mcp](https://github.com/xpzouying/xiaohongshu-mcp) | `xiaohongshu-mcp/` | ZIP 解压副本，无 `.git` | 本机 MCP 服务，通过 Rod 浏览器自动化库驱动有界面或无界面浏览器 |
| [goofish-cli](https://github.com/fancyboi999/goofish-cli) | `goofish-cli/` | ZIP 解压副本，无 `.git` | 命令行工具，原生支持 MCP |
| [ai-goofish-monitor](https://github.com/Usagi-org/ai-goofish-monitor) | `ai-goofish-monitor/` | ZIP 解压副本，无 `.git` | 监控系统＋网页后台，使用 Playwright 浏览器自动化工具与 AI 分析 |
| [MediaCrawler](https://github.com/NanmiCoder/MediaCrawler) | `MediaCrawler/` | ZIP 解压副本，无 `.git` | 多平台自媒体爬虫，本机浏览器 / Chrome 开发者工具协议（CDP，用于连接并控制现有浏览器），可供智能体技能编排调用 |

ZIP 解压目录已统一去掉 `-main`、`-master` 分支后缀，仅保留项目名；重命名不改变源码内容或获取方式。这些副本仍无 Git 历史，具体提交未知，不能认定它们与远端最新版本一致。

## 各自解决什么问题

### 1. last30days-skill：海外讨论定题

检索近约 30 天的海外讨论，覆盖 Reddit、X、YouTube、Hacker News（HN，技术社区）、Polymarket（预测市场）和网页等来源，合成为带出处的研究报告。适合英文市场舆情、热点与选题研究；具体来源是否可用取决于依赖、密钥及登录配置。小红书渠道需显式选入并连接兼容且已登录的外部服务，海外版不能仅靠安装 Python Playwright 直接搜索小红书。

### 2. last30days-skill-cn：中文舆情与热点扫描

默认面向微博、小红书、B站、知乎、抖音、微信公众号、百度、今日头条八个平台，检索近期讨论并生成报告，另有全网热榜。适合扫描用户抱怨、近期热点和跨平台观点差异。

热榜反映当前榜单，主题研究按时间窗口检索，两者不是同一种样本。登录采集、热榜匹配与公开搜索回退的覆盖程度不同，报告中的来源缺失、日期与互动数据限制应一并保留。

### 3. Agent-Reach：定题后的搜索与单篇补读

为智能体提供多渠道搜索和阅读能力，覆盖 B站、V2EX、GitHub、YouTube、通用网页等，并可按配置接入小红书、雪球、Boss、LinkedIn、Reddit 等。适合定题后补读帖子、文章或视频内容，不作为批量评论爬虫使用；可用渠道以实际配置和检查结果为准。

### 4. social-media-copilot：多平台登录态采集

开源插件支持小红书、抖音、快手的内容、评论及用户等数据采集，适合在已有登录状态下补充短视频、图文平台证据。

需区分版本：本地 `social-media-copilot/` 是主分支开源插件；接口调用与自部署方案位于上游 `server`（服务端）分支，可按该分支说明选择 Docker 容器部署。商店版、开源版和服务端版的功能不能直接等同，也不能把本机主分支副本视为已部署的接口服务。

### 5. xiaohongshu-mcp：独立的小红书工具服务

提供登录、登录状态检查、笔记搜索、详情读取及发布、评论等能力，可作为其他调研工具的小红书数据入口，是否接通仍需配置验证。

适合需要独立 MCP 服务的本机调用场景。云服务器出口可能触发验证码，优先考虑本机网络与独立小号；有界面模式也便于人工处理登录和验证。服务端直接在本机运行，不要求作者云端中转。

### 6. goofish-cli：闲鱼商品查询与智能体编排

将闲鱼（Goofish）的商品搜索、详情查询及运营操作封装为结构化命令，并支持 MCP 调用。适合明确品类后的二手市场检索、转卖侧观察和智能体编排。

商品检索反映供给、挂牌价格及描述，不等于已验证的真实成交或付费需求；它也不承担跨平台讨论报告的职责。

### 7. ai-goofish-monitor：长期盯盘与筛选通知

按关键词、价格等条件持续或定时监控闲鱼商品，通过 AI 筛选分析，配合网页后台管理任务、账号、结果与通知。适合长期找货、观察新品上架及跟踪特定品类，不是讨论报告的主路径。

### 8. MediaCrawler：定题后的评论级深挖

通过本机浏览器采集小红书、抖音、快手、B站、微博、贴吧、知乎等平台的帖子与评论，支持二级评论、关键词搜索、指定帖子及创作者主页采集，可导出逗号分隔表格（CSV）、结构化数据（JSON）等原料。使用 Playwright 登录并保存登录状态，也可通过 CDP 连接已有浏览器，供智能体技能编排调用。

适合锁定话题后的评论级深挖，提取“求推荐、踩雷、想要但没有、愿意付费”等需求证据；采集结果仍需后续分析，本身不负责搜索讨论并合成研究报告。本地配置 `ENABLE_CDP_MODE = True`、`ENABLE_GET_COMMENTS = True`、`ENABLE_GET_SUB_COMMENTS = False`，即已配置浏览器连接与评论采集，二级评论需要另行开启；这些配置不代表已成功运行。

本机已有 ZIP 解压源码，目录已从 `MediaCrawler-main/` 改为 `MediaCrawler/`，无需重复克隆；后续若需要 Git 更新能力，再另行安排获取方式。

## 怎么配合使用

1. **先定题。** 中文市场用 last30days-skill-cn，英文市场用 last30days-skill，先找热点、抱怨与观点分歧，保留原始出处。
2. **再补证据。** 用 Agent-Reach 补读单篇；需要小红书登录态时，优先检查 xiaohongshu-mcp 共享服务；需要小红书、抖音、快手数据采集时再评估 social-media-copilot 对应版本。
3. **深挖评论。** 定题后用 MediaCrawler 按关键词、帖子或作者采集评论原料，按需开启二级评论，并保留来源供后续分析。
4. **商品侧单独观察。** 有明确品类后，用 goofish-cli 做按需检索；需要长期追踪时再考虑 ai-goofish-monitor。把商品信号与讨论证据分别记录，再交叉判断。

以上是建议分工，不代表这八个项目已在本机互相接通，也不代表它们都能完整抓取平台评论。

## 更新与仓库边界

- **Git 克隆：** 更新前先在项目目录检查 `git status`，确认本地改动和分支后再执行 `git pull`；保留各项目自己的版本管理。
- **ZIP 解压副本：** 没有 Git 历史，不能直接 `git pull`。需要更新时另行下载并对比，保留本地改动与配置；不要直接覆盖现有副本。
- **父仓库：** 不把这些上游源码加入 `evolution_lab`。误加入带 `.git` 的目录可能只记录嵌套仓库指针；误加入 ZIP 副本则可能将整份源码作为普通文件提交。忽略规则不会自动取消对已跟踪文件的跟踪。

本说明只整理源码用途与本机存放方式；具体安装、账号登录、权限、依赖及运行命令，以对应副本中的说明为准。

## radar 接入与验证

八项按需接入方式见父项目 `SKILL.md` 及 `references/`；本地实测状态见父项目 `VALIDATION.md`。源码存在不代表已经安装、登录或完成真实采集。国内外对照由 radar 分别调用中文源与海外版，不再由中文版重复桥接海外源。
