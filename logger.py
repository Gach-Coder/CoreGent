"""
日志模块 —— 将 Agent 每一次 LLM 调用与工具执行的完整链路写入 log.txt。

记录内容:
  • 用户输入原文
  • 每一轮 LLM 调用的完整输入 messages（含 system/user/assistant/tool）
  • DeepSeek 返回的原始输出（content + tool_calls 完整 JSON）
  • 工具调用的参数与执行结果
  • 每轮结束后的 context 快照（所有 messages 摘要）
  • 最终回复

日志文件: 项目根目录下的 log.txt，追加写入（不覆盖历史记录）。
"""

import json
import os
from datetime import datetime
from typing import Any

# ---- 分隔线 ----
SEP = "=" * 72
SEP2 = "-" * 72


class AgentLogger:
    """Agent 专用日志器，写入 log.txt 并可选回显到终端。"""

    def __init__(self, log_path: str = "log.txt", echo: bool = False):
        """
        Args:
            log_path: 日志文件路径。
            echo: 是否同步输出到终端（默认仅写文件）。
        """
        self.log_path = log_path
        self.echo = echo
        self._rotation_check()

    # ---------- 内部 ----------

    def _rotation_check(self):
        """若 log.txt 超过 5MB，备份后新建。"""
        try:
            if os.path.exists(self.log_path) and os.path.getsize(self.log_path) > 5 * 1024 * 1024:
                bak = f"{self.log_path}.{datetime.now().strftime('%Y%m%d_%H%M%S')}.bak"
                os.rename(self.log_path, bak)
                self._write(f"(日志文件超过 5MB，已备份至 {bak})\n")
        except OSError:
            pass

    def _write(self, text: str):
        """写入文件（追加模式，UTF-8）。"""
        os.makedirs(os.path.dirname(self.log_path) or ".", exist_ok=True)
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(text)

    def _emit(self, text: str):
        """写入日志文件 + 可选终端回显。"""
        self._write(text)
        if self.echo:
            print(text, end="", flush=True)

    def _pretty_json(self, obj: Any) -> str:
        """美化 JSON，对 tool_calls/function 字段重点展开。"""
        return json.dumps(obj, ensure_ascii=False, indent=2)

    def _msg_summary(self, msg: dict) -> str:
        """将单条 message 压缩为一行摘要，避免日志爆炸。"""
        role = msg.get("role", "?")
        content = msg.get("content")

        if role == "tool":
            cid = msg.get("tool_call_id", "?")
            # 截断过长的工具结果
            if content and len(content) > 500:
                content = content[:500] + f"\n... (共 {len(content)} 字符，已截断)"
            return f"[{role}] tool_call_id={cid}\n{content}\n"

        if role == "assistant" and msg.get("tool_calls"):
            tc_names = [tc["function"]["name"] for tc in msg["tool_calls"]]
            extra = f" + tool_calls: {tc_names}"
            if content:
                return f"[{role}] content='{content[:120]}'{extra}"
            return f"[{role}] (no content){extra}"

        if content:
            if len(content) > 300:
                return f"[{role}] {content[:300]}\n... (共 {len(content)} 字符，已截断)"
            return f"[{role}] {content}"

        return f"[{role}] (empty)"

    # ---------- 公开 API ----------

    def session_start(self):
        """写入会话开始标记。"""
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._emit(f"\n{SEP}\n  SESSION START — {ts}\n{SEP}\n")

    def user_input(self, text: str):
        """记录用户输入。"""
        self._emit(f"\n┌─ USER INPUT {SEP2}\n")
        self._emit(f"│ {text}\n")
        self._emit(f"└{SEP2}\n")

    def llm_input(self, round_idx: int, messages: list[dict]):
        """记录第 N 轮发给 LLM 的完整 messages。"""
        self._emit(f"\n┌─ [ROUND {round_idx}] LLM INPUT —— 发送给模型的 messages "
                   f"({len(messages)} 条) {SEP2}\n")
        for i, msg in enumerate(messages):
            self._emit(f"\n│ msg[{i}] {self._msg_summary(msg)}")
        self._emit(f"\n├─ INPUT END (共 {len(messages)} messages){SEP2}\n")

    def llm_raw_output(self, round_idx: int, msg: Any):
        """记录模型返回的原始 message 对象（content + tool_calls 完整 JSON）。"""
        self._emit(f"\n┌─ [ROUND {round_idx}] LLM RAW OUTPUT —— 模型原始返回 {SEP2}\n")

        # content
        content = getattr(msg, "content", None)
        self._emit(f"\n│ content: {repr(content)}\n")

        # tool_calls 完整 dump
        raw_tool_calls = getattr(msg, "tool_calls", None)
        if raw_tool_calls:
            self._emit(f"│ tool_calls ({len(raw_tool_calls)} 个):\n")
            for tc in raw_tool_calls:
                tc_dict = {
                    "id": tc.id,
                    "type": tc.type,
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                self._emit(f"│ {self._pretty_json(tc_dict)}\n")
        else:
            self._emit("\n│ tool_calls: None  (模型未请求工具调用)\n")

        # 如果模型直接返回了文本（没有 tool_calls），这就是最终回复
        if content and not raw_tool_calls:
            self._emit(f"\n│ → 模型直接返回文本（无工具调用），此即最终回复\n")

        self._emit(f"└{SEP2}\n")

    def tool_execution(self, round_idx: int, tool_name: str, args: dict, result: str):
        """记录单次工具执行。"""
        self._emit(f"\n┌─ [ROUND {round_idx}] TOOL EXECUTION {SEP2}\n")
        self._emit(f"│ 工具名: {tool_name}\n")
        self._emit(f"│ 参数:   {self._pretty_json(args)}\n")
        self._emit(f"│ 结果:\n")
        for line in result.splitlines():
            self._emit(f"│   {line}\n")
        self._emit(f"└{SEP2}\n")

    def context_snapshot(self, round_idx: int, messages: list[dict]):
        """记录本轮结束后的完整 context 快照。"""
        self._emit(f"\n┌─ [ROUND {round_idx}] CONTEXT SNAPSHOT —— 当前对话历史 "
                   f"({len(messages)} 条) {SEP2}\n")
        for i, msg in enumerate(messages):
            self._emit(f"\n│ [{i}] {self._msg_summary(msg)}")
        self._emit(f"└{SEP2}\n")

    def final_output(self, text: str):
        """记录最终回复。"""
        self._emit(f"\n┌─ FINAL OUTPUT {SEP2}\n")
        self._emit(f"│ {text}\n")
        self._emit(f"└{SEP2}\n")

    def error(self, message: str):
        """记录错误。"""
        self._emit(f"\n┌─ ERROR {SEP2}\n")
        self._emit(f"│ {message}\n")
        self._emit(f"└{SEP2}\n")

    def max_rounds_exceeded(self, max_rounds: int):
        """记录超出最大轮次。"""
        self._emit(f"\n┌─ LIMIT REACHED {SEP2}\n")
        self._emit(f"│ 已达到最大工具调用轮次 ({max_rounds})，强制终止。\n")
        self._emit(f"└{SEP2}\n")

    def reset(self):
        """记录对话重置。"""
        self._emit(f"\n┌─ RESET {SEP2}\n")
        self._emit(f"│ 对话历史已重置\n")
        self._emit(f"└{SEP2}\n")

    def llm_stream_output(
        self,
        round_idx: int,
        content: str | None,
        reasoning_content: str | None,
        tool_calls: list[dict] | None,
        finish_reason: str | None,
    ):
        """记录流式模式下的模型输出（组装后的完整结果）。"""
        self._emit(
            f"\n┌─ [ROUND {round_idx}] LLM STREAM OUTPUT —— "
            f"流式组装结果 {SEP2}\n"
        )

        if reasoning_content:
            self._emit(f"\n│ reasoning_content ({len(reasoning_content)} 字符):\n")
            for line in reasoning_content.splitlines():
                self._emit(f"│   {line}\n")

        if content:
            self._emit(f"\n│ content ({len(content)} 字符):\n")
            for line in content.splitlines():
                self._emit(f"│   {line}\n")

        if tool_calls:
            self._emit(f"│ tool_calls ({len(tool_calls)} 个):\n")
            for tc in tool_calls:
                self._emit(f"│ {self._pretty_json(tc)}\n")
        else:
            self._emit("\n│ tool_calls: None  (模型未请求工具调用)\n")

        if content and not tool_calls:
            self._emit(f"\n│ → 模型直接返回文本（无工具调用），此即最终回复\n")

        self._emit(f"│ finish_reason: {finish_reason}\n")
        self._emit(f"└{SEP2}\n")

    def note(self, message: str):
        """记录一条备注/警告（如 finish_reason 异常等）。"""
        self._emit(f"\n┌─ NOTE {SEP2}\n")
        for line in message.splitlines():
            self._emit(f"│ {line}\n")
        self._emit(f"└{SEP2}\n")
