# MDCNG Grok 适配器

这是一个面向 MDCNG 的轻量级 OpenAI-compatible API 适配服务。它位于 MDCNG 与 sub2api 之间，用于在配置的 Grok 类模型请求缺少 `stream:false` 时自动补充该字段，并将 Grok JSON 响应标准化，或将上游 SSE 响应转换为普通 Chat Completions JSON。

## 请求链路

```text
MDCNG -> mdcng-adapter -> sub2api -> grok2api
```

MDCNG 中请配置为：

```text
Base URL: http://mdcng-adapter:8080/v1
API Key: 继续使用 sub2api 的 API Key
```

## 项目文档

- [需求规格说明书](docs/requirements.md)
- [临时 Prompt 调试日志需求说明](docs/debug-prompt-logging.md)
- [贡献与提交规范](CONTRIBUTING.md)

## 功能

- `GET /health` 返回 `{"ok": true}`。
- `POST /v1/chat/completions` 将 OpenAI-compatible Chat 请求转发到 sub2api。
- 仅当以下条件全部满足时，自动补充 `"stream": false`：
  - 请求路径是 `/v1/chat/completions`
  - 请求方法是 `POST`
  - 请求体是 JSON object
  - 模型名以 `GROK_MODEL_PREFIXES` 中的任一前缀开头
  - 请求体中不存在 `stream` 字段
  - `FORCE_STREAM_FALSE=true`
- 将目标模型的 JSON 响应清洗为标准 Chat Completions 结构。
- 将目标模型的 `text/event-stream` 响应聚合为 `application/json`。
- 非目标模型默认透传，例如 `gpt-5.4-mini`。
- 透传其他路径，例如 `/v1/models`、`/v1/embeddings`、`/v1/audio/...`。

## 配置项

| 变量 | 默认值 | 说明 |
|---|---|---|
| `SUB2API_BASE_URL` | `http://sub2api:8080` | 上游 sub2api 基础地址 |
| `TZ` | `Asia/Singapore` | 容器时区，Docker Compose 默认设置 |
| `GROK_MODEL_PREFIXES` | `grok` | 需要适配的模型名前缀，多个前缀用逗号分隔 |
| `FORCE_STREAM_FALSE` | `true` | 目标模型请求缺少 `stream` 字段时是否补充 `stream:false` |
| `CLEAN_GROK_RESPONSE` | `true` | 是否清洗目标模型的 JSON/SSE 响应 |
| `PASSTHROUGH_NON_GROK` | `true` | 非目标模型是否默认透传 |
| `LOG_LEVEL` | `info` | Python 日志级别 |
| `REQUEST_TIMEOUT` | `120` | 上游请求超时时间，单位秒 |
| `CLEAN_ALL_RESPONSES` | `false` | 是否清洗所有模型的响应 |
| `MAX_ERROR_PREVIEW_CHARS` | `1000` | 响应解析失败时返回的上游响应预览最大字符数 |
| `MAX_UPSTREAM_RESPONSE_BYTES` | `33554432` | 上游响应最大字节数，超过后返回 502 |
| `MAX_SSE_EVENTS` | `4096` | SSE 聚合最大事件数 |
| `MAX_SSE_CONTENT_CHARS` | `1048576` | SSE 聚合后的内容最大字符数 |
| `DEBUG_LOG_PROMPT` | `false` | 是否临时输出 Chat 请求的 prompt 调试预览 |
| `DEBUG_LOG_PROMPT_MAX_CHARS` | `1000` | 每段 system/user prompt 预览最大字符数 |

### 临时 Prompt 调试日志

默认不会输出 `messages`、system prompt 或 user prompt。排查 MDCNG 实际传给模型的 prompt 时，可临时开启：

```yaml
DEBUG_LOG_PROMPT: "true"
DEBUG_LOG_PROMPT_MAX_CHARS: "1000"
```

开启后，`/v1/chat/completions` 会额外输出一条 `prompt_debug=true` 日志，包含 `model`、`messages_count`、`system_prompt_count`、`user_prompt_count`、`system_prompt_preview`、`user_prompt_preview`、`temperature`、`max_tokens`、`stream` 和 `prompt_truncated`。

安全注意事项：该日志可能包含标题、简介、标签、演员等业务内容，只建议临时开启；排查完成后请改回 `DEBUG_LOG_PROMPT: "false"` 或删除相关配置。日志不会输出完整请求体、完整响应体或完整 API Key。

## 本地开发

安装依赖：

```bash
python -m pip install -r requirements-dev.txt
```

运行测试：

```bash
python -m pytest
```

## 贡献与提交规范

提交信息统一使用以下格式：

```text
<type>: 中文说明
```

详细规范见 [CONTRIBUTING.md](CONTRIBUTING.md)。

本地启动服务：

```bash
set SUB2API_BASE_URL=http://localhost:8081
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

PowerShell 示例：

```powershell
$env:SUB2API_BASE_URL = "http://localhost:8081"
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

## Docker Compose 部署

```bash
docker compose up -d --build
```

当前 `docker-compose.yml` 默认使用镜像：

```text
ghcr.io/chasesgp/mdcng-adapter:latest
```

同时保留 `build: .`，方便本地构建时给镜像打同名标签。

当前 `docker-compose.yml` 默认使用名为 `mdcng-network` 的外部 Docker 网络。请确保 MDCNG、mdcng-adapter 和 sub2api 在该网络中可以互相访问。

日志使用 Docker 默认 `json-file` 驱动，并在 `docker-compose.yml` 中启用轮转：

```yaml
logging:
  driver: json-file
  options:
    max-size: "10m"
    max-file: "7"
```

该配置限制单个日志文件最大 10MB，最多保留 7 个日志文件。Docker Compose 原生不支持按天数精确保留日志；如需严格按天清理，需要使用宿主机 `logrotate` 或 Loki、Fluent Bit 等外部日志系统。

## GitHub Actions 多架构镜像

仓库已提供 GitHub Actions workflow：

```text
.github/workflows/docker-image.yml
```

该 workflow 使用 Docker Buildx 构建以下平台镜像：

```text
linux/amd64
linux/arm64
```

默认推送到 GitHub Container Registry：

```text
ghcr.io/<owner>/<repo>
```

触发规则：

- 推送到 `main` 或 `master` 分支时构建并推送镜像。
- 推送 `v*` 标签时构建并推送镜像。
- Pull Request 会先运行测试，再构建验证镜像，但不推送镜像。
- 也可以在 GitHub Actions 页面手动触发 `workflow_dispatch`。

常见镜像标签：

- 默认分支：`latest`
- 分支名：例如 `main`
- Git 标签：例如 `v1.0.0`
- 提交 SHA：例如 `sha-xxxxxxx`

## 验证示例

健康检查：

```bash
curl http://localhost:8080/health
```

Grok 请求：

```bash
curl -s http://localhost:8080/v1/chat/completions \
  -H "Authorization: Bearer sk-test" \
  -H "Content-Type: application/json" \
  -d '{"model":"grok-4.20-0309-non-reasoning-console","messages":[{"role":"user","content":"hi"}]}'
```

预期行为：

- 如果原请求缺少 `stream` 字段，转发给上游的请求体应包含 `"stream":false`
- 返回给 MDCNG 的响应应为 `Content-Type: application/json`
- `usage` 中只包含 `prompt_tokens`、`completion_tokens` 和 `total_tokens`

GPT 透传请求：

```bash
curl -s http://localhost:8080/v1/chat/completions \
  -H "Authorization: Bearer sk-test" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-5.4-mini","messages":[{"role":"user","content":"hi"}]}'
```

预期日志字段包含：

```text
passthrough=true stream_modified=false response_cleaned=false
```

## 错误响应

Chat 请求体不是合法 JSON：

```json
{"error":{"message":"invalid json request body","type":"invalid_request_error"}}
```

上游不可达：

```json
{"error":{"message":"upstream request failed","type":"upstream_error"}}
```

上游响应超过限制：

```json
{"error":{"message":"upstream response too large","type":"upstream_response_too_large","max_bytes":33554432}}
```

清洗响应时无法解析上游响应：

```json
{
  "error": {
    "message": "adapter failed to parse upstream response",
    "type": "adapter_parse_error",
    "upstream_status": 200,
    "upstream_content_type": "text/plain",
    "upstream_body_preview": "..."
  }
}
```
