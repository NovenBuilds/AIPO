# Quickstart

在仓库根目录。

## 回放

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_aipo -v
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s legacy/topic-signal-radar/tests -v
```

期望：服务测试和旧雷达测试都通过。回放报告含“登记：回放。本任务没有实采结果。”

## 模型管线

测试用本地兼容接口检查规划、深读和引用。这不是一次真实模型验收。真实模型需要：

- `AIPO_MODEL_BASE_URL`
- `AIPO_MODEL_NAME`
- `AIPO_MODEL_API_KEY`

密钥不要写入配置文件。

## 实采诊断

```bash
python3 -m aipo doctor --probe
python3 -m aipo fingerprint
```

小红书看健康检查和登录状态。闲鱼看本机是否有 `goofish`，以及 `auth status` 是否有效。没有登录就停止，不要把回放样例记成实采。

## 一次手动调用

```bash
python3 -m aipo serve
```

调用方发送 `start_research`，问题使用交接里的微信小程序句子，然后用 `get_research` 看报告。需要继续时用 `resume_research`。
