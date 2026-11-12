# AIPO · 商机研究服务

给服务一句话，由它自行规划研究、调用现有平台能力、交叉核对证据，并交付有出处的中文商机报告。服务对智能体提供一个 MCP（模型上下文协议）入口，首版覆盖 AIPO 话题信号雷达已登记的平台和来源类型。

## 从这里开始

- [服务启动](docs/服务启动.md) · [模型配置](docs/模型配置.md) · [技能入口切换](docs/技能入口切换.md)
- [平台与能力对应](docs/平台能力对应.md) · [阶段检查点](docs/验收/阶段检查点.md)
- [给 Grok Bot 的交接与验收](docs/Grok交接.md)
- [架构、工作流程与工具契约](docs/架构与契约.md)
- [全量上游、平台矩阵与实测基线](docs/平台与依赖.md) · [可读取的依赖清单](docs/依赖清单.json)
- [迁入的旧代码、技能与项目背景](legacy/README.md)

一句话从 MCP（模型上下文协议）的 `start_research` 进入。服务自己选择来源、归档证据并返回中文报告。调用方不要再分别调用各平台工具。

```bash
python3 -m aipo serve
```

示例配置 `configs/aipo.example.json` 的模式是回放。回放报告会写明不是实采。有平台权限时再把 `mode` 改成 `live`。

## 跑测试

服务测试：

    PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_aipo -v

迁入基线的离线测试：

    PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s legacy/topic-signal-radar/tests -v

真实平台验收逐来源记录搜索、正文、评论或商品字段及当次登录状态。离线回放与历史实采结果分别记录。
