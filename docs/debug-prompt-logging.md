# MDCNG Adapter 临时 Prompt 调试日志需求说明

## 1. 背景

当前 MDCNG 通过 `mdcng-adapter` 调用上游 sub2api：

```text
MDCNG -> mdcng-adapter -> sub2api -> 上游模型服务
```

MDCNG 中配置的 Base URL 为：

```text
http://mdcng-adapter:8080/v1
```

当前 `mdcng-adapter` 主要负责：

- 自动补充 Grok 请求缺失的 `stream:false`
- 清洗 Grok JSON 响应
- 聚合 SSE 响应为普通 JSON
- 透传非 Grok 请求

但当前 adapter 日志默认不会输出 MDCNG 请求体中的：

```text
messages
system prompt
user prompt
temperature
max_tokens
```

因此无法直接判断 MDCNG 调用 AI 翻译时是否传递了合适的 System Prompt。由于当前翻译质量不理想，需要临时观察 MDCNG 实际发给模型的 prompt 内容。

重点确认：

- 是否存在 `role=system`
- System Prompt 是否过于泛化
- User Prompt 是否明确说明翻译任务
- 标题、简介、标签、演员、片商等信息是否一起传给模型
- `temperature`、`max_tokens` 等参数是否合理

## 2. 目标

新增一个默认关闭的调试功能，用于临时记录 MDCNG 发来的 Chat Completions 请求中的 prompt 预览。

目标：

- 默认不输出 prompt，避免泄露敏感内容。
- 仅在显式开启配置时输出 prompt 预览。
- 能看到 `system` 和 `user` 消息内容的截断预览。
- 能看到请求中的关键参数，例如 `model`、`temperature`、`max_tokens`。
- 不记录完整 API Key。
- 不记录完整请求体。
- 不记录完整响应体。
- 抓包排查完成后可以关闭。

## 3. 非目标

本功能不负责：

- 修改 MDCNG 发出的 prompt。
- 自动优化翻译质量。
- 自动注入 System Prompt。
- 修改 sub2api 或上游模型服务。
- 长期保存请求内容。
- 实现完整审计日志系统。
- 替代专业日志平台。

本功能仅用于临时排查 MDCNG 发给模型的实际 prompt 内容。

## 4. 配置项设计

新增环境变量：

| 变量 | 默认值 | 说明 |
|---|---:|---|
| `DEBUG_LOG_PROMPT` | `false` | 是否开启 prompt 调试日志 |
| `DEBUG_LOG_PROMPT_MAX_CHARS` | `1000` | 每段 prompt 最大输出字符数 |

### 4.1 `DEBUG_LOG_PROMPT`

默认值：

```text
false
```

开启方式：

```yaml
DEBUG_LOG_PROMPT: "true"
```

关闭方式：

```yaml
DEBUG_LOG_PROMPT: "false"
```

建议只在排查时临时开启，抓完后关闭。

### 4.2 `DEBUG_LOG_PROMPT_MAX_CHARS`

默认值：

```text
1000
```

作用：限制每段 system/user prompt 输出的最大字符数。

例如：

```yaml
DEBUG_LOG_PROMPT_MAX_CHARS: "1000"
```

如果配置非法，例如：

```text
DEBUG_LOG_PROMPT_MAX_CHARS=abc
DEBUG_LOG_PROMPT_MAX_CHARS=0
```

应回退默认值：

```text
1000
```

## 5. Docker Compose 示例

临时开启 prompt 调试时，在 `mdcng-adapter` 的环境变量中设置：

```yaml
services:
  mdcng-adapter:
    environment:
      DEBUG_LOG_PROMPT: "true"
      DEBUG_LOG_PROMPT_MAX_CHARS: "1000"
```

排查完成后建议改回：

```yaml
DEBUG_LOG_PROMPT: "false"
```

或者直接删除这两个调试配置。

## 6. 日志输出内容

开启后，每次 `/v1/chat/completions` 请求会额外输出一条 prompt 调试日志。

字段：

| 字段 | 说明 |
|---|---|
| `prompt_debug` | 固定为 `true` |
| `model` | 请求模型名 |
| `messages_count` | messages 数量 |
| `system_prompt_count` | system 消息数量 |
| `user_prompt_count` | user 消息数量 |
| `system_prompt_preview` | system prompt 截断预览 |
| `user_prompt_preview` | user prompt 截断预览 |
| `temperature` | 请求 temperature |
| `max_tokens` | 请求 max_tokens |
| `stream` | 请求 stream 字段 |
| `prompt_truncated` | 是否发生截断 |

示例：

```text
prompt_debug=true model=grok-4.20-0309-non-reasoning-console messages_count=2 system_prompt_count=1 user_prompt_count=1 system_prompt_preview=You are a helpful assistant. user_prompt_preview=Translate the following title and overview... temperature=0.2 max_tokens=2048 stream=false prompt_truncated=false
```

如果没有 system prompt：

```text
prompt_debug=true model=grok-xxx messages_count=1 system_prompt_count=0 user_prompt_count=1 system_prompt_preview=- user_prompt_preview=Translate this... temperature=0.2 max_tokens=2048 stream=false prompt_truncated=false
```

## 7. 内容处理规则

### 7.1 只记录预览

不得记录完整请求体。只记录：

```text
system prompt preview
user prompt preview
```

每段最多输出 `DEBUG_LOG_PROMPT_MAX_CHARS` 个字符。超出时截断并追加：

```text
...
```

### 7.2 转义换行和制表符

为了避免日志格式被污染，prompt 内容中的特殊字符需要转义：

| 原字符 | 输出 |
|---|---|
| 回车 | `\r` |
| 换行 | `\n` |
| 制表符 | `\t` |

例如原文：

```text
第一行
第二行
```

日志中输出：

```text
第一行\n第二行
```

### 7.3 不记录 Authorization

不得在 prompt 调试日志中输出完整：

```text
Authorization
API Key
Bearer Token
```

现有普通请求日志可以继续使用脱敏格式：

```text
Bearer sk-****abcd
```

### 7.4 非字符串 content 处理

OpenAI-compatible 的 `message.content` 可能不一定是字符串，例如可能是数组或对象。

规则：

- `content` 是字符串：正常截断输出。
- `content` 不是字符串：输出类型提示，不展开完整内容。

例如：

```text
system_prompt_preview=<non-string content: list>
```

这样可以避免日志意外输出复杂结构或过大内容。

## 8. 安全注意事项

该功能有敏感信息风险。因为 prompt 中可能包含：

- 影片标题
- 简介
- 标签
- 演员名
- 片商
- 用户输入内容
- 其他业务数据

所以必须遵守：

1. 默认关闭。
2. 只临时开启。
3. 只输出截断预览。
4. 不输出完整请求体。
5. 不输出完整响应体。
6. 不输出完整 API Key。
7. 抓完问题后立即关闭。
8. 注意 Docker 日志轮转仍可能短期保存这些内容。

当前 Docker Compose 日志轮转配置为：

```yaml
logging:
  driver: json-file
  options:
    max-size: "10m"
    max-file: "7"
```

这意味着 prompt 调试日志可能会保存在最近约 70MB 的 Docker 日志中。

## 9. 排查使用流程

### 9.1 开启调试

在 `docker-compose.yml` 中临时设置：

```yaml
DEBUG_LOG_PROMPT: "true"
DEBUG_LOG_PROMPT_MAX_CHARS: "1000"
```

重启 adapter：

```bash
docker compose up -d
```

### 9.2 观察日志

```bash
docker logs -f mdcng-adapter
```

### 9.3 在 MDCNG 中触发一次 AI 翻译

触发标题或简介翻译。

### 9.4 检查日志

重点看：

```text
system_prompt_preview
user_prompt_preview
temperature
max_tokens
```

### 9.5 关闭调试

抓完后改回：

```yaml
DEBUG_LOG_PROMPT: "false"
```

然后重启：

```bash
docker compose up -d
```

## 10. 验收标准

### 10.1 默认不输出 prompt

当：

```text
DEBUG_LOG_PROMPT=false
```

日志中不应出现：

```text
prompt_debug=true
system_prompt_preview
user_prompt_preview
```

### 10.2 开启后输出 prompt 预览

当：

```text
DEBUG_LOG_PROMPT=true
```

请求中存在：

```json
{
  "role": "system",
  "content": "You are a helpful assistant."
}
```

日志中应能看到：

```text
system_prompt_preview=You are a helpful assistant.
```

### 10.3 没有 system prompt 时明确显示

如果 messages 中没有 `role=system`，日志中应显示：

```text
system_prompt_count=0
system_prompt_preview=-
```

### 10.4 超长 prompt 会被截断

当 prompt 超过 `DEBUG_LOG_PROMPT_MAX_CHARS`，日志中应只输出截断内容，并标记：

```text
prompt_truncated=true
```

### 10.5 换行会被转义

原始 prompt：

```text
第一行
第二行
```

日志输出：

```text
第一行\n第二行
```

### 10.6 不输出 API Key

日志中不得出现完整：

```text
sk-xxxxxxxx
```

只允许脱敏：

```text
Bearer sk-****abcd
```

或完全不输出 Authorization。

## 11. 后续扩展方向

如果确认 MDCNG 的 System Prompt 太弱，可以后续再考虑新增独立功能：

```text
INJECT_SYSTEM_PROMPT=true
SYSTEM_PROMPT_FILE=/config/system_prompt.txt
```

但这是另一个功能，不建议和本次“临时抓 prompt 日志”混在一起。本次只做观察，不改写请求内容。
