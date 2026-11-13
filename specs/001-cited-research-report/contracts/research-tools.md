# 研究入口

对外仍是三个工具，输入和返回不新增字段。

| 工具 | 必填 | 可选 | 成功时调用方看到 |
| --- | --- | --- | --- |
| start_research | question | request_id、platforms | 任务编号、状态、是否复用 |
| get_research | research_id | 无 | 状态、阶段、来源进度；定稿或草稿中的中文报告 |
| resume_research | research_id | answer | 原任务继续；已完成则说明未重新取证 |

相同 request_id 且问题、平台、模式都相同才复用。任一不同返回冲突说明。

实采失败不得返回回放夹具中的标题或价格。
