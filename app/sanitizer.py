from __future__ import annotations

import time
import uuid
from typing import Any

from .config import Settings


BUILTIN_PROMPT_FIELD_TITLE = "标题"
BUILTIN_PROMPT_FIELD_OVERVIEW = "简介"


def infer_mdcng_field_type(content: str) -> str:
    text = content.strip()
    if not text:
        return BUILTIN_PROMPT_FIELD_OVERVIEW

    lowered = text.lower()
    if any(marker in lowered for marker in ("<br", "<p", "</p", "<div", "</div", "<li", "</li")):
        return BUILTIN_PROMPT_FIELD_OVERVIEW
    if "\n" in text or "\r" in text:
        return BUILTIN_PROMPT_FIELD_OVERVIEW

    sentence_marks = sum(text.count(mark) for mark in ("。", "！", "？", "!", "?"))
    if sentence_marks >= 2:
        return BUILTIN_PROMPT_FIELD_OVERVIEW
    if len(text) >= 140:
        return BUILTIN_PROMPT_FIELD_OVERVIEW

    return BUILTIN_PROMPT_FIELD_TITLE


def build_builtin_system_prompt(field_type: str) -> str:
    normalized_field_type = (
        field_type
        if field_type in {BUILTIN_PROMPT_FIELD_TITLE, BUILTIN_PROMPT_FIELD_OVERVIEW}
        else BUILTIN_PROMPT_FIELD_OVERVIEW
    )
    field_rule = (
        "当前字段是标题。最终结果必须是适合媒体库展示的简体中文短标题，建议18到24个汉字，不超过30个汉字；"
        "先理解原意再改写，不要逐词硬译；只保留核心人物、关系、场景、行为或卖点中的关键要素；"
        "删除夸张修饰、宣传语、感叹语、重复词和次要细节；禁止输出句号、引号、括号、书名号和其他装饰性符号。"
        if normalized_field_type == BUILTIN_PROMPT_FIELD_TITLE
        else "当前字段是简介。最终结果必须是适合媒体库展示的简体中文单段简介，建议120到220个汉字；"
        "先理解原意再概括改写，不要逐句直译；保留核心剧情、人物关系、场景和主要行为，合并重复或同类卖点；"
        "删除夸张宣传、主观吹捧、销售话术、感叹语和无信息量修饰；禁止换行、分段、标题和列表。"
    )

    return f"""
你是 mdcng-adapter 内置的成人影片标题与简介翻译、清洗与本地化专员。

字段判定已由 adapter 完成：当前字段：{normalized_field_type}。
{field_rule}

必须严格遵守：
1. 只处理 user 消息中的原始文本，不要调用工具，不要使用网络搜索、web_search、外部资料、搜索来源或站点页面。
2. 不要补全 user 消息中没有的信息，不要根据番号、演员或标题自行查询剧情。
3. 输出必须统一为自然、准确、流畅、简洁的简体中文，语气像媒体库标题/简介，不像广告文案。
4. 输入若是日语、英语、繁体中文或其他非简体中文，必须翻译为简体中文；若已经是简体中文，只做清洗、纠错和润色。
5. 删除 HTML 标签、emoji、乱码、装饰符号、广告、促销、官网链接、下载提示、观看引导、站点残留和模板残留。
6. 全角字符尽量转为半角字符；只保留必要的常用中文标点；删除「」【】《》『』“”‘’[]()（）等不适合媒体库展示的引号、括号、书名号和装饰性符号。
7. 演员名有稳定通用中文译名时可使用中文译名，没有通用译名则保留原文，不得臆造。
8. 成人内容按原意自然表达，不刻意回避敏感词，但要避免生硬直译、日式断句和粗糙词语堆砌；遇到遮挡字或谐音词时，根据上下文改写成自然中文，无法确定则泛化表达。
9. 优先使用第三人称客观表述，减少“你”“您”“男人愿望”“极致体验”等代入式或煽动式表达。
10. 只输出最终结果，不输出原文、语言判断、字段判断、解释、备注、Markdown、引号、前缀或后缀。
11. 最终输出必须是一行文本。
""".strip()


def is_target_model(model: object, prefixes: tuple[str, ...]) -> bool:
    if not isinstance(model, str):
        return False
    normalized = model.lower()
    return any(normalized.startswith(prefix) for prefix in prefixes)


def sanitize_chat_request(body: dict[str, Any], settings: Settings) -> tuple[dict[str, Any], bool, bool]:
    model = body.get("model")
    target_model = is_target_model(model, settings.grok_model_prefixes)
    stream_modified = False

    if target_model and settings.force_stream_false and "stream" not in body:
        body = dict(body)
        body["stream"] = False
        stream_modified = True

    if target_model:
        body = _replace_builtin_prompt_if_triggered(body, settings)

    return body, stream_modified, target_model


def _replace_builtin_prompt_if_triggered(body: dict[str, Any], settings: Settings) -> dict[str, Any]:
    messages = body.get("messages")
    trigger = settings.builtin_prompt_trigger.strip()
    if not trigger or not isinstance(messages, list):
        return body

    if not _has_builtin_prompt_trigger(messages, trigger):
        return body

    field_type = infer_mdcng_field_type(_collect_user_content(messages))
    builtin_prompt = build_builtin_system_prompt(field_type)
    updated = dict(body)
    updated["messages"] = _replace_system_messages(messages, builtin_prompt, trigger)
    updated["temperature"] = settings.builtin_prompt_temperature
    updated["max_tokens"] = (
        settings.builtin_prompt_title_max_tokens
        if field_type == BUILTIN_PROMPT_FIELD_TITLE
        else settings.builtin_prompt_overview_max_tokens
    )
    if settings.builtin_prompt_disable_search:
        _remove_search_options(updated)
    return updated


def _has_builtin_prompt_trigger(messages: list[object], trigger: str) -> bool:
    return any(
        isinstance(message, dict)
        and message.get("role") == "system"
        and isinstance(message.get("content"), str)
        and message["content"].strip() == trigger
        for message in messages
    )


def _collect_user_content(messages: list[object]) -> str:
    parts: list[str] = []
    for message in messages:
        if not isinstance(message, dict) or message.get("role") != "user":
            continue
        content = message.get("content")
        if isinstance(content, str):
            parts.append(content)
    return "\n".join(parts)


def _replace_system_messages(messages: list[object], builtin_prompt: str, trigger: str) -> list[object]:
    replaced_messages: list[object] = []
    inserted = False

    for message in messages:
        if not isinstance(message, dict) or message.get("role") != "system":
            replaced_messages.append(message)
            continue

        content = message.get("content")
        if not inserted and isinstance(content, str) and content.strip() == trigger:
            replacement = dict(message)
            replacement["content"] = builtin_prompt
            replaced_messages.append(replacement)
            inserted = True

    if not inserted:
        return [{"role": "system", "content": builtin_prompt}, *replaced_messages]
    return replaced_messages


def _remove_search_options(body: dict[str, Any]) -> None:
    tools = body.get("tools")
    if isinstance(tools, list):
        filtered_tools = [tool for tool in tools if not _is_search_tool(tool)]
        if filtered_tools:
            body["tools"] = filtered_tools
        else:
            body.pop("tools", None)

    tool_choice = body.get("tool_choice")
    if _is_search_tool_choice(tool_choice):
        body["tool_choice"] = "none"

    body.pop("search_parameters", None)
    body.pop("web_search_options", None)


def _is_search_tool(tool: object) -> bool:
    if not isinstance(tool, dict):
        return False

    tool_type = tool.get("type")
    if isinstance(tool_type, str) and tool_type.lower() in {"web_search", "x_search"}:
        return True

    function = tool.get("function")
    if isinstance(function, dict):
        function_name = function.get("name")
        return isinstance(function_name, str) and function_name.lower() in {"web_search", "x_search"}

    return False


def _is_search_tool_choice(tool_choice: object) -> bool:
    if isinstance(tool_choice, str):
        return tool_choice.lower() in {"web_search", "x_search"}
    if not isinstance(tool_choice, dict):
        return False

    function = tool_choice.get("function")
    if isinstance(function, dict):
        function_name = function.get("name")
        return isinstance(function_name, str) and function_name.lower() in {"web_search", "x_search"}

    tool_type = tool_choice.get("type")
    return isinstance(tool_type, str) and tool_type.lower() in {"web_search", "x_search"}


def standard_usage(usage: object | None = None) -> dict[str, int]:
    if not isinstance(usage, dict):
        usage = {}
    prompt_tokens = _to_int(usage.get("prompt_tokens"))
    completion_tokens = _to_int(usage.get("completion_tokens"))
    total_tokens = _to_int(usage.get("total_tokens"), prompt_tokens + completion_tokens)
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }


def sanitize_chat_completion_response(data: dict[str, Any], request_model: str | None = None) -> dict[str, Any]:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        choices = [
            {
                "index": 0,
                "message": {"role": "assistant", "content": ""},
                "finish_reason": "stop",
            }
        ]

    return {
        "id": _string_or_default(data.get("id"), _adapter_id()),
        "object": "chat.completion",
        "created": _to_int(data.get("created"), int(time.time())),
        "model": _string_or_default(data.get("model"), request_model or ""),
        "choices": [_sanitize_choice(choice, index) for index, choice in enumerate(choices)],
        "usage": standard_usage(data.get("usage")),
    }


def build_chat_completion_response(
    *,
    model: str | None,
    contents_by_index: dict[int, str] | None = None,
    roles_by_index: dict[int, str] | None = None,
    finish_reasons_by_index: dict[int, str] | None = None,
    response_id: str | None = None,
    created: int | None = None,
    usage: object | None = None,
) -> dict[str, Any]:
    contents_by_index = contents_by_index or {0: ""}
    roles_by_index = roles_by_index or {}
    finish_reasons_by_index = finish_reasons_by_index or {}
    choices = []

    for choice_index in sorted(contents_by_index):
        choices.append(
            {
                "index": choice_index,
                "message": {
                    "role": roles_by_index.get(choice_index, "assistant"),
                    "content": contents_by_index.get(choice_index, ""),
                },
                "finish_reason": finish_reasons_by_index.get(choice_index, "stop"),
            }
        )

    if not choices:
        choices.append(
            {
                "index": 0,
                "message": {"role": "assistant", "content": ""},
                "finish_reason": "stop",
            }
        )

    return {
        "id": response_id or _adapter_id(),
        "object": "chat.completion",
        "created": created or int(time.time()),
        "model": model or "",
        "choices": choices,
        "usage": standard_usage(usage),
    }


def _sanitize_choice(choice: object, fallback_index: int) -> dict[str, Any]:
    if not isinstance(choice, dict):
        choice = {}

    message = choice.get("message")
    if not isinstance(message, dict):
        message = choice.get("delta") if isinstance(choice.get("delta"), dict) else {}

    return {
        "index": _to_int(choice.get("index"), fallback_index),
        "message": {
            "role": _string_or_default(message.get("role"), "assistant"),
            "content": _content_to_text(message.get("content")),
        },
        "finish_reason": _string_or_default(choice.get("finish_reason"), "stop"),
    }


def _content_to_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _to_int(value: object, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _string_or_default(value: object, default: str) -> str:
    return value if isinstance(value, str) and value else default


def _adapter_id() -> str:
    return f"chatcmpl-adapter-{uuid.uuid4().hex}"
