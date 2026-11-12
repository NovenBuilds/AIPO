# 本机小红书调用卡

常规读取用本页和[平台共同规则](../platform-access.md)。从当前宿主工具获取输入契约；已配置服务的地址与认证使用现有安全配置。容器名不是接口标识，不为查询改配置或启动新服务。

## 按需调用

| 目的 | 当前只读工具 | 要点 |
| --- | --- | --- |
| 验证登录 | `check_login_status` | 实际返回决定本轮会话状态 |
| 获取二维码 | `get_login_qrcode` | 仅缺登录时使用，按返回有效期扫码 |
| 关键词搜索 | `search_feeds` | `keyword`及可选`filters`以当前契约为准 |
| 正文、图片及评论 | `get_feed_detail` | `feed_id`、`xsec_token`来自真实搜索或首页，不编造 |
| 首页笔记 | `list_feeds` | 仅任务需要首页时调用，不当额外验收步骤 |

搜索和首篇详情直接服务研究并计入采样。已有工具可调用时，不先读上游README或运行全量环境探针。

## 数量与读取深度

- 已验版本搜索一页返回20张卡片，没有“每组10篇”参数；三组可能超出共同规则上限。继续搜索前按剩余额度处理，不直接做三次再截断。
- 默认详情返回前10条一级评论及随带回复。`load_all_comments=true`时`limit`才生效；是否展开回复等仍看当前契约。记录实际评论总数及`hasMore`，不能把`limit`当工具保证的硬上限。
- 搜索日期筛选不等于精确近30天；保留实际窗口。只向分析层展示必要卡片字段；深读时读取真实正文、关键配图和评论，不以摘要代替。

## 登录与故障

本机已安装[双击登录入口](<~/Library/Application Support/xiaohongshu-mcp/登录小红书.command>)，可由用户运行，在本机预览二维码；入口缺失时用当前服务的二维码工具。普通浏览器登录不自动共享给服务。

协议排障才查[上游README](../../upstream/xiaohongshu-mcp/README.md)、[路由](../../upstream/xiaohongshu-mcp/routes.go)及处理代码。已有直接接口：登录`/api/v1/login/status`、二维码`/api/v1/login/qrcode`用GET，搜索`/api/v1/feeds/search`支持GET/POST，详情`/api/v1/feeds/detail`用POST。认证沿用现有配置，不将密钥放入URL或输出。

最近实战为2026-11-04的v2.7.0，读取链路通过；仅代表当次范围，详见[验收记录](../../VALIDATION.md)。当次工具契约或失败结果与本页不符时再定位源码，不凭历史成功继续扩采。
