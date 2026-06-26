# MDCNG Grok 兼容适配器需求规格说明书

## 1. 文档信息

| 项目 | 内容 |
|---|---|
| 项目名称 | MDCNG Grok 兼容适配器 |
| 服务名称 | `mdcng-adapter` |
| 文档类型 | 需求规格说明书 |
| 文档版本 | v1.0.0 |
| 文档状态 | 正式版 |
| 适用范围 | MDCNG 通过 OpenAI-compatible API 调用 Grok 类模型的兼容适配场景 |

## 2. 项目背景

当前环境中，MDCNG 通过 OpenAI-compatible API 调用 sub2api，再由 sub2api 转发到不同上游模型服务。

现有调用链路：

```text
MDCNG -> sub2api -> 上游模型服务
```

现有模型测试结果：

| 模型 | 结果 |
|---|---|
| `gpt-5.4-mini` | 正常 |
| `grok-4.20-0309-non-reasoning-console` | MDCNG 测试失败 |

经过抓包和日志排查，MDCNG 对 GPT 和 Grok 发送的请求结构基本一致，主要差异为模型名。

MDCNG 发送的 Grok 请求示例：

```json
{
  "messages": [
    {
      "role": "system",
      "content": "You are a helpful assistant."
    },
    {
      "role": "user",
      "content": "..."
    }
  ],
  "model": "grok-4.20-0309-non-reasoning-console",
  "max_tokens": 2048,
  "temperature": 0.2
}
```

问题点在于 MDCNG 请求体中没有显式传递：

```json
{
  "stream": false
}
```

对 Grok 上游的测试结果表明：

```text
请求未显式传 stream:false -> Grok 返回 text/event-stream
请求显式传 stream:false -> Grok 返回 application/json
```

MDCNG 的测试连接逻辑按普通 JSON 响应解析。当 Grok 返回 SSE 流式响应时，MDCNG 报错：

```text
failed to deserialize api response: expected value at line 1 column 1
```

因此需要新增一个 MDCNG 专用适配服务，在 MDCNG 和 sub2api 之间做请求和响应兼容处理。

## 3. 项目目标

建设一个轻量级 OpenAI-compatible API 适配服务，作为 MDCNG 和 sub2api 之间的中间层。

目标调用链路：

```text
MDCNG -> mdcng-adapter -> sub2api -> grok2api
```

核心目标：

- 对 Grok 类模型请求自动补充缺失的 `stream:false`。
- 将 Grok 类模型响应清洗为 MDCNG 易于解析的标准 Chat Completions JSON。
- 将上游 SSE 响应聚合为普通 JSON 响应。
- 保持非 Grok 模型默认透传，避免影响已有 GPT 模型。
- 不修改 MDCNG、sub2api 或 grok2api 源码。

## 4. 范围说明

### 4.1 目标范围

本项目负责：

- 接收 MDCNG 发出的 OpenAI-compatible API 请求。
- 将请求转发到 sub2api。
- 对命中的 Grok 类模型请求进行必要清洗。
- 对命中的 Grok 类模型响应进行必要清洗。
- 对上游 SSE 响应进行兼容聚合。
- 对非目标模型和其他接口进行默认透传。

### 4.2 非目标范围

本项目不负责：

- 修改 MDCNG 源码。
- 修改 sub2api 源码。
- 修改 grok2api 全局行为。
- 实现鉴权系统。
- 实现模型计费。
- 实现管理后台。
- 长期保存请求或响应内容。

## 5. 功能需求

### 5.1 请求转发

适配器必须接收 MDCNG 发来的 OpenAI-compatible 请求，并转发到 sub2api。

默认上游地址：

```text
http://sub2api:8080
```

MDCNG 配置中的 Base URL 应改为：

```text
http://mdcng-adapter:8080/v1
```

API Key 仍沿用 sub2api 的 API Key。

### 5.2 请求清洗

当请求同时满足以下条件时，适配器必须自动补充 `stream:false`：

| 条件 | 要求 |
|---|---|
| 请求路径 | `/v1/chat/completions` |
| 请求方法 | `POST` |
| 请求体 | 合法 JSON object |
| 模型名 | 以配置的 Grok 类前缀开头 |
| `stream` 字段 | 请求体中不存在 |
| 配置开关 | `FORCE_STREAM_FALSE=true` |

处理前示例：

```json
{
  "messages": [
    {
      "role": "user",
      "content": "hi"
    }
  ],
  "model": "grok-4.20-0309-non-reasoning-console",
  "max_tokens": 2048,
  "temperature": 0.2
}
```

处理后示例：

```json
{
  "messages": [
    {
      "role": "user",
      "content": "hi"
    }
  ],
  "model": "grok-4.20-0309-non-reasoning-console",
  "max_tokens": 2048,
  "temperature": 0.2,
  "stream": false
}
```

如果请求体中已经存在 `stream` 字段，适配器不应覆盖客户端原始值。

### 5.3 响应清洗

适配器需要将 sub2api 返回的 Grok 类模型响应转换为 MDCNG 容易解析的标准 OpenAI Chat Completions JSON 格式。

标准响应结构：

```json
{
  "id": "chatcmpl-xxx",
  "object": "chat.completion",
  "created": 1782426849,
  "model": "grok-4.20-0309-non-reasoning-console",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Hi!"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 1935,
    "completion_tokens": 21,
    "total_tokens": 1956
  }
}
```

清洗要求：

- 保留标准 Chat Completions 字段。
- 移除或忽略 MDCNG 不需要的非标准扩展字段。
- `usage` 只保留以下字段：
  - `prompt_tokens`
  - `completion_tokens`
  - `total_tokens`
- 不应返回以下字段：
  - `usage.prompt_tokens_details`
  - `usage.completion_tokens_details`

### 5.4 SSE 响应兼容

如果上游返回：

```text
Content-Type: text/event-stream
```

适配器必须解析 SSE 数据，并将多个 `data:` chunk 合并为一个普通 JSON 响应。

SSE 输入示例：

```text
data: {"choices":[{"delta":{"role":"assistant","content":"Hi"}}]}
data: {"choices":[{"delta":{"content":"!"}}]}
data: [DONE]
```

适配器输出示例：

```json
{
  "id": "chatcmpl-adapter-xxx",
  "object": "chat.completion",
  "created": 1782426849,
  "model": "grok-4.20-0309-non-reasoning-console",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Hi!"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0
  }
}
```

### 5.5 非目标模型透传

对于非 Grok 类模型，例如：

```text
gpt-5.4-mini
```

适配器默认应原样转发请求和响应，不做额外修改。

可通过配置项控制是否对所有模型做响应清洗，默认关闭。

## 6. 接口需求

### 6.1 健康检查接口

```http
GET /health
```

响应：

```json
{
  "ok": true
}
```

### 6.2 Chat Completions 转发接口

```http
POST /v1/chat/completions
```

处理流程：

1. 接收 MDCNG 请求。
2. 解析请求体 JSON。
3. 判断模型是否命中目标前缀。
4. 必要时补充 `stream:false`。
5. 转发请求到 sub2api。
6. 接收 sub2api 响应。
7. 必要时清洗 JSON 响应或聚合 SSE 响应。
8. 返回 MDCNG 可解析的响应。

### 6.3 其他接口透传

除 `/v1/chat/completions` 外，其他路径默认透传到 sub2api，例如：

```text
/v1/models
/v1/embeddings
/v1/audio/...
```

## 7. 配置需求

配置项通过环境变量提供。

| 变量 | 默认值 | 说明 |
|---|---|---|
| `SUB2API_BASE_URL` | `http://sub2api:8080` | 上游 sub2api 地址 |
| `TZ` | `Asia/Singapore` | 容器时区，Docker Compose 默认设置 |
| `GROK_MODEL_PREFIXES` | `grok` | 需要特殊处理的模型名前缀，多个前缀用逗号分隔 |
| `FORCE_STREAM_FALSE` | `true` | 是否对目标模型自动补充 `stream:false` |
| `CLEAN_GROK_RESPONSE` | `true` | 是否清洗目标模型响应 |
| `PASSTHROUGH_NON_GROK` | `true` | 非目标模型是否完全透传 |
| `LOG_LEVEL` | `info` | 日志级别 |
| `REQUEST_TIMEOUT` | `120` | 请求上游超时时间，单位秒 |
| `CLEAN_ALL_RESPONSES` | `false` | 是否清洗所有模型响应 |
| `MAX_ERROR_PREVIEW_CHARS` | `1000` | 上游响应解析失败时 body preview 最大字符数 |
| `MAX_UPSTREAM_RESPONSE_BYTES` | `33554432` | 上游响应最大字节数，超过后返回 502 |
| `MAX_SSE_EVENTS` | `4096` | SSE 聚合最大事件数 |
| `MAX_SSE_CONTENT_CHARS` | `1048576` | SSE 聚合后的内容最大字符数 |
| `DEBUG_LOG_PROMPT` | `false` | 是否临时输出 Chat 请求的 prompt 调试预览 |
| `DEBUG_LOG_PROMPT_MAX_CHARS` | `1000` | 每段 system/user prompt 预览最大字符数 |

## 8. Header 处理要求

适配器转发请求时应保留必要 header：

```text
Authorization
Content-Type
Accept
OpenAI-Beta
User-Agent
```

适配器应移除或重写以下 header：

```text
Host
Content-Length
Accept-Encoding
Connection
Transfer-Encoding
```

推荐设置：

```text
Accept-Encoding: identity
Content-Type: application/json
```

这样可以避免上游返回 gzip/br 压缩数据导致适配器解析困难。

## 9. 日志要求

适配器应记录以下信息：

- 请求时间。
- 请求路径。
- 请求方法。
- 模型名。
- 是否补充 `stream:false`。
- 上游响应状态码。
- 上游 `Content-Type`。
- 是否执行响应清洗。
- 请求耗时。
- 错误信息。

日志中必须避免输出完整 API Key。

`Authorization` header 需要脱敏，例如：

```text
Bearer sk-****abcd
```

## 10. 错误处理要求

### 10.1 上游不可达

HTTP 状态码：

```text
502
```

响应：

```json
{
  "error": {
    "message": "upstream request failed",
    "type": "upstream_error"
  }
}
```

### 10.2 上游响应无法解析

HTTP 状态码：

```text
502
```

响应：

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

### 10.3 请求体不是合法 JSON

仅针对 `/v1/chat/completions`。

HTTP 状态码：

```text
400
```

响应：

```json
{
  "error": {
    "message": "invalid json request body",
    "type": "invalid_request_error"
  }
}
```

### 10.4 上游响应超过大小限制

HTTP 状态码：

```text
502
```

响应：

```json
{
  "error": {
    "message": "upstream response too large",
    "type": "upstream_response_too_large",
    "max_bytes": 33554432
  }
}
```

## 11. 部署要求

建议使用 Docker Compose 部署。

服务名：

```text
mdcng-adapter
```

服务端口：

```text
8080
```

示例调用链路：

```text
MDCNG Base URL: http://mdcng-adapter:8080/v1
mdcng-adapter upstream: http://sub2api:8080
```

部署要求：

```text
mdcng-adapter 与 MDCNG、sub2api 至少应处于可互相访问的 Docker 网络中
```

## 12. 验收标准

### 12.1 健康检查

请求：

```http
GET /health
```

应返回：

```json
{
  "ok": true
}
```

### 12.2 GPT 模型不受影响

MDCNG 使用：

```text
gpt-5.4-mini
```

应正常测试通过。

适配器日志应显示：

```text
passthrough=true
stream_modified=false
response_cleaned=false
```

### 12.3 Grok 模型请求自动补充 stream:false

MDCNG 使用：

```text
grok-4.20-0309-non-reasoning-console
```

适配器转发给 sub2api 的请求体中应包含：

```json
"stream": false
```

### 12.4 Grok 模型返回 application/json

适配器返回给 MDCNG 的响应应为：

```text
Content-Type: application/json
```

而不是：

```text
Content-Type: text/event-stream
```

### 12.5 MDCNG Grok 测试通过

MDCNG 中 Grok 模型 AI 测试不再出现：

```text
failed to deserialize api response: expected value at line 1 column 1
```

### 12.6 usage 字段被简化

返回给 MDCNG 的 `usage` 应只包含：

```json
{
  "prompt_tokens": 0,
  "completion_tokens": 0,
  "total_tokens": 0
}
```

或真实 token 值。

响应中不应包含：

```text
prompt_tokens_details
completion_tokens_details
```

## 13. 推荐技术栈

推荐使用：

```text
Python 3.12
FastAPI
httpx
uvicorn
Docker Compose
```

可选方案：

```text
Node.js + Express/Fastify
Go + net/http
```

技术选型优先级：

```text
简单可维护 > 性能极致
```

本服务只做轻量 JSON 转发和清洗，Python FastAPI 已足够。
