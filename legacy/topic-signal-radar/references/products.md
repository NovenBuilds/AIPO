# 闲鱼商品观察与监控结果

## goofish-cli：按需查询

读取 `upstream/goofish-cli/README.md` 与对应命令帮助。使用已有环境或为该项目按需准备专用环境，不默认采用 Docker 沙箱或全局安装。先检查 `goofish auth status`，只记录有效与否，不保存或展示会话值。

只读入口：`goofish search items <关键词>`、`goofish item get <ID>`、`goofish item view <ID>`。格式、数量限制以本机帮助为准。默认一个关键词、至多 5 件商品的小样本，用户明确扩大才增加。命令行与 MCP 二选一使用已具备的入口，不自动注册新的宿主服务。

不读取买家私信，不发布、下架、上传、发消息或交易。遇验证停止。结果标记 access=product，保留商品链接、型号、成色、挂牌价格及观察时间；价格不放入互动 metrics，也不能写成成交价格。

## ai-goofish-monitor：只接已有结果

读取 `upstream/ai-goofish-monitor/README.md`。监控系统独立管理账号、任务、AI、通知与数据库。radar 不启动后台、不创建或启停任务，不搭 webhook 接收服务。

用户在已有后台导出 CSV，或明确提供 JSON/JSONL 结果路径后，先读字段和样例。CSV 导出可参考本地 `src/api/routes/results.py`；不假定旧 jsonl 目录仍是在线主存储，也不直接修改 SQLite。

把用户导出文件作为 raw_files 归档，提取商品 URL、描述、价格等证据，标记 access=monitor_result。AI 推荐文字只是上游判断，不等于商品真实状态。若导出不含可定位商品链接，可保留原文件并说明证据不足，不伪造链接。

## 与讨论交叉分析

分别呈现用户讨论与商品观察。比较“使用痛点”和“转卖描述”的一致或分歧，写明挂牌价、转卖原因真实性与成交情况仍未验证。商品快照的观察时间不等于商品发布日期。
