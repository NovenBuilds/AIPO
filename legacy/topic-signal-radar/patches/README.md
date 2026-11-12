# 上游本地适配补丁

形成日期：2026-10-24。上游 `Jesseovo/last30days-skill-cn` 基线为 `af785c682de2fb9192e495daf061308a7a6799ec`。

`last30days-cn-preflight.patch` 保存此前已经存在的根 SKILL.md 与生成副本的环境预检规则修改：检查 Python 版 Playwright、隔离安装、验证浏览器、本人登录、准确解释降级。此次重构未重置上游或改写其运行代码。

父仓库忽略上游，所以补丁单独保留。更新上游之前先检查其 Git 状态，保留本地改动；不要自动 pull/reset 或重复应用。可在该上游目录使用 `git apply --unidiff-zero --reverse --check <补丁绝对路径>` 验证当前修改已存在，或在干净且兼容的基线上用 `git apply --unidiff-zero --check` 检查可应用性。冲突需人工对齐，不能覆盖。


## 2026-11-03：本地读取路线清理

- `last30days-local-service-only.patch`：基于 last30days `f3cd06a620e385ce15109ed6d3b70fc20c89eccc`，移除已退役浏览器插件的设置说明、运行时修复提示及各语言指南引用，统一指向兼容本机服务。未改变采集协议和模型调用逻辑。
- `xiaohongshu-local-service-only.patch`：对应本地ZIP副本的中英文README，移除已退役浏览器插件的推荐段和外链；未改动服务实现。ZIP提交未知，不能直接宣称兼容远端任意版本。

这些是用户要求的本地适配；更新上游先核对本地差异与补丁，不能自动覆盖或重复应用。当前源码可用 `git apply --reverse --check <补丁>` 检查适配是否已存在。旧补丁保持不变。
