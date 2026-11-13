# Research: 带引用的商机研究报告

## 模型何时参与

- Decision: 沿用 `aipo/model.py` 的 OpenAI 兼容聊天接口。已配置地址、模型名和密钥时，依次请求规划、深读选择和判断。未配置或输出不合法时，保留程序计划和程序简报。
- Rationale: 架构已规定模型理解问题、选择样本、生成判断，程序控制预算和引用。现有实现只附加一段补充，没有完成这三步。
- Alternatives considered: 换一个新的模型供应商。放弃，因为密钥和环境变量约定已经写在模型配置里。

## 来源选择的边界

- Decision: 程序先按问题和平台生成允许的来源。模型可以改关键词，也可以去掉用户没有点名的来源，但不能新增来源，也不能去掉用户点名的平台。
- Rationale: 章程要求复用已登记来源，并且指定平台不可用时不能用别的样本顶替。
- Alternatives considered: 让模型自由选平台。放弃，那会超出首版矩阵。

## 深读选择

- Decision: 只在实采路径把模型选择交给小红书详情和闲鱼 `item get`。回放继续使用固定夹具。候选编号不在返回列表里时，退回程序的默认上限。
- Rationale: 回放验收已经固定了样例正文和评论。把模型选择应用到回放会让同一夹具变成不稳定结果。
- Alternatives considered: 回放也按模型选择裁剪夹具。放弃，因为那会把回放和实采混在同一条不确定路径上。

## 闲鱼价格字段

- Decision: v0.6.0 的详情把接口里的 `soldPrice` 映射成输出字段 `price`，并另有 `price_kind`。这里的 `price` 记录为挂牌价。`status` 含已售、售出、卖掉或 sold 时记录为平台公开标记。卖家描述记录为卖家自述。四类都不是独立核验成交，除非材料原文写明独立核验成交。
- Rationale: 上游归一化代码把 `soldPrice` 当作商品标价，同时用 `defaultPrice` 区分一口价和可议价。产品说明要求价格不写成成交价。
- Alternatives considered: 见到 `soldPrice` 就写成成交。放弃，字段名和成交核验不是一回事。

## 登录状态

- Decision: `goofish auth status --format json` 只有 `valid` 为真才搜索。归档只保留是否有效，不保留账号标识。无法解析时不搜索。
- Rationale: 现有产品说明要求先检查登录，并且不保存或展示会话值。该命令在登录失效时仍可能以成功退出码返回 `valid: false`。
- Alternatives considered: 只看退出码。放弃，因为退出码不能区分“命令成功但未登录”。
