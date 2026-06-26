"""
核心智能体模块 —— 封装 DeepSeek 模型调用与工具执行循环。

Agent 的工作流程:
  1. 接收用户输入
  2. 发送给 DeepSeek（携带工具定义）
  3. 若模型返回 tool_calls → 本地执行工具 → 将结果回传 → 回到步骤 2
  4. 若模型返回文本回复 → 结束，返回最终答案

支持:
  - 多轮工具调用（最多 MAX_TOOL_ROUNDS 轮）
  - 完整的对话历史追踪
  - 每一步的详细日志写入 log.txt（LLM 输入 / 原始输出 / 工具执行 / context 快照）
"""

import json
from openai import OpenAI
from tools import TOOL_DEFINITIONS, TOOL_MAP, register_mcp_tools, unregister_mcp_tools
from logger import AgentLogger
import config


class Agent:
    """基于 DeepSeek 的智能体，支持工具调用。"""

    def __init__(
        self,
        system_prompt: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        log_path: str = "log.txt",
        log_echo: bool = False,
        stream: bool = True,
    ):
        """
        Args:
            system_prompt: 系统提示词，设定 Agent 的行为与角色。
            api_key: DeepSeek API 密钥，默认从 config 读取。
            base_url: API 端点，默认从 config 读取。
            model: 模型名称，默认从 config 读取。
            log_path: 日志文件路径，默认 log.txt。
            log_echo: 是否同时输出日志到终端，默认 False。
            stream: 是否启用流式输出，默认 True。
                    开启后 reasoning_content 和正文内容均实时输出。
        """
        self.api_key = api_key or config.API_KEY
        self.base_url = base_url or config.BASE_URL
        self.model = model or config.MODEL
        self.stream = stream

        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)

        self.system_prompt = system_prompt or (
            "你是一个实用的 AI 助手，可以调用工具来完成用户的任务。"
            "当用户请求执行操作时，使用合适的工具执行。"
            "如果工具返回错误，如实告知用户并尝试其他方案。"
        )

        # 对话历史
        self.messages: list[dict] = [
            {"role": "system", "content": self.system_prompt}
        ]

        # 日志器
        self.logger = AgentLogger(log_path=log_path, echo=log_echo)
        self.logger.session_start()

        # ---- MCP 集成 ----
        self._mcp_manager = None
        self._init_mcp()

        # 轮次计数器（跨 run() 调用递增）
        self._global_round = 0

        # Token 追踪
        self._total_tokens = 0

    # ================================================================
    # 内部方法
    # ================================================================

    def _dump_message_for_history(self, msg) -> dict:
        """将 OpenAI message 对象转为可序列化的 dict 存入 messages 列表。"""
        record: dict = {"role": "assistant", "content": msg.content}
        if msg.tool_calls:
            record["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in msg.tool_calls
            ]
        return record

    def _execute_tool(self, tool_call) -> str:
        """执行单个工具调用并返回结果字符串。

        Args:
            tool_call: OpenAI tool_call 对象，含 id / function.name / function.arguments。

        Returns:
            工具执行结果字符串。
        """
        name = tool_call.function.name
        try:
            args = json.loads(tool_call.function.arguments)
        except json.JSONDecodeError:
            return f"错误: 工具参数解析失败: {tool_call.function.arguments}"

        func = TOOL_MAP.get(name)
        if func is None:
            return f"错误: 未知工具 '{name}'，可用工具: {list(TOOL_MAP.keys())}"

        try:
            return func(**args)
        except TypeError as e:
            return f"错误: 工具 '{name}' 参数不匹配: {e}"
        except Exception as e:
            return f"错误: 工具 '{name}' 执行异常: {e}"

    def _execute_tool_dict(self, tool_call: dict) -> str:
        """执行单个工具调用（dict 格式，用于流式模式下的 tool_calls）。

        Args:
            tool_call: {"id": ..., "function": {"name": ..., "arguments": ...}}

        Returns:
            工具执行结果字符串。
        """
        name = tool_call["function"]["name"]
        try:
            args = json.loads(tool_call["function"]["arguments"])
        except json.JSONDecodeError:
            return f"错误: 工具参数解析失败: {tool_call['function']['arguments']}"

        func = TOOL_MAP.get(name)
        if func is None:
            return f"错误: 未知工具 '{name}'，可用工具: {list(TOOL_MAP.keys())}"

        try:
            return func(**args)
        except TypeError as e:
            return f"错误: 工具 '{name}' 参数不匹配: {e}"
        except Exception as e:
            return f"错误: 工具 '{name}' 执行异常: {e}"

    # ---- MCP 管理 ----

    def _init_mcp(self) -> None:
        """初始化 MCP 连接并注册工具。

        失败时降级运行（仅内置工具可用），不阻断 Agent 启动。
        """
        if not config.MCP_ENABLED:
            return

        try:
            from mcp_client import MCPClientManager
            self._mcp_manager = MCPClientManager()
            connected = self._mcp_manager.connect_all()
            if connected:
                count = register_mcp_tools(self._mcp_manager)
                self.logger.note(
                    f"MCP 集成: 已连接 {self._mcp_manager.server_count} "
                    f"台服务器，注册 {count} 个工具"
                )
            else:
                self.logger.note("MCP 集成: 无服务器连接成功，仅使用内置工具")
        except ImportError as e:
            self.logger.note(f"MCP 集成: 缺少 mcp 包 ({e})，仅使用内置工具")
        except Exception as e:
            self.logger.note(f"MCP 集成: 初始化失败 ({e})，仅使用内置工具")

    def _cleanup_mcp(self) -> None:
        """断开 MCP 连接并恢复内置工具列表。"""
        if self._mcp_manager is not None:
            try:
                unregister_mcp_tools()
                self._mcp_manager.disconnect_all()
            except Exception:
                pass
            self._mcp_manager = None

    # ---- LLM 调用 ----

    def _call_llm_streaming(self, round_idx: int, stream_callback=None):
        """流式调用 DeepSeek，实时输出 reasoning_content 和正文内容。

        Args:
            round_idx: 日志轮次索引。
            stream_callback: 可选回调，签名 cb(event_type, data)。
                event_type: "reasoning" | "content" | "tool_call"
                data: {"text": str} 或 {"name": str, "arguments": str}

        遍历 SSE 事件流，累积:
          - content_parts: 正文片段列表
          - reasoning_parts: 思考过程片段列表
          - tool_calls_acc: 按 index 累积的工具调用

        Returns:
            dict: {
                'content': str | None,
                'reasoning_content': str | None,
                'tool_calls': list[dict] | None,
                'finish_reason': str | None,
            }
        """
        response = self.client.chat.completions.create(
            model=self.model,
            messages=self.messages,
            tools=TOOL_DEFINITIONS,
            temperature=config.TEMPERATURE,
            max_tokens=config.MAX_TOKENS,
            stream=True,
            stream_options={"include_usage": True},
        )

        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        tool_calls_acc: dict[int, dict] = {}
        finish_reason: str | None = None
        reasoning_started = False
        content_started = False

        for chunk in response:
            if not chunk.choices:
                continue

            delta = chunk.choices[0].delta
            chunk_finish = chunk.choices[0].finish_reason

            # ---- reasoning_content (DeepSeek R1 思考过程) ----
            rc = getattr(delta, "reasoning_content", None)
            if rc:
                if not reasoning_started:
                    print("\n  [🧠 思考过程]", flush=True)
                    print("  " + "-" * 40, flush=True)
                    reasoning_started = True
                reasoning_parts.append(rc)
                print(rc, end="", flush=True)
                if stream_callback:
                    stream_callback("reasoning", {"text": rc})

            # ---- 正文内容 ----
            if delta.content:
                if reasoning_started and not content_started:
                    print("\n  " + "-" * 40, flush=True)
                    print("  [💬 回复]\n", flush=True)
                    content_started = True
                elif not reasoning_started and not content_started:
                    content_started = True
                content_parts.append(delta.content)
                print(delta.content, end="", flush=True)
                if stream_callback:
                    stream_callback("content", {"text": delta.content})

            # ---- 工具调用（增量拼接） ----
            if delta.tool_calls:
                if reasoning_started or content_started:
                    print(flush=True)
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in tool_calls_acc:
                        tool_calls_acc[idx] = {
                            "id": "",
                            "type": "function",
                            "function": {"name": "", "arguments": ""},
                        }
                    acc = tool_calls_acc[idx]
                    if tc_delta.id:
                        acc["id"] += tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            acc["function"]["name"] += tc_delta.function.name
                        if tc_delta.function.arguments:
                            acc["function"]["arguments"] += tc_delta.function.arguments

            # ---- usage（流式末 chunk 含 token 统计） ----
            if hasattr(chunk, "usage") and chunk.usage:
                self._total_tokens += chunk.usage.total_tokens

            # ---- finish_reason（最后一个 chunk） ----
            if chunk_finish:
                finish_reason = chunk_finish

        # ---- 收尾换行 ----
        if reasoning_started or content_started:
            print(flush=True)

        # ---- 组装结果 ----
        full_content = "".join(content_parts) if content_parts else None
        full_reasoning = "".join(reasoning_parts) if reasoning_parts else None

        tool_calls = None
        if tool_calls_acc:
            tool_calls = [
                tool_calls_acc[i] for i in sorted(tool_calls_acc.keys())
            ]

        # ---- 记录 LLM 原始输出到日志 ----
        self.logger.llm_stream_output(
            round_idx, full_content, full_reasoning, tool_calls, finish_reason
        )

        return {
            "content": full_content,
            "reasoning_content": full_reasoning,
            "tool_calls": tool_calls,
            "finish_reason": finish_reason,
        }

    # ================================================================
    # 公开方法
    # ================================================================

    def run(self, user_input: str, stream_callback=None) -> str:
        """处理一条用户输入，执行完整的 Agent 循环，返回最终回复。

        每一步都会将详细信息写入 log.txt:
          - 用户输入
          - 每轮 LLM 输入 messages
          - 模型原始输出（content + tool_calls JSON）
          - 工具参数与执行结果
          - 每轮结束后的 context 快照
          - 最终文本回复

        Args:
            user_input: 用户的自然语言请求。
            stream_callback: 可选回调，签名 cb(event_type, data)。
                用于 Web UI 等场景的流式推送。
                event_type: "reasoning" | "content" | "tool_call" |
                            "tool_result" | "done" | "error"

        Returns:
            Agent 的最终文本回复。
        """
        # ---- 记录用户输入 ----
        self.messages.append({"role": "user", "content": user_input})
        self.logger.user_input(user_input)

        for round_idx in range(config.MAX_TOOL_ROUNDS):
            self._global_round += 1
            r = self._global_round

            # ---- 记录 LLM 输入 ----
            self.logger.llm_input(r, self.messages)

            # ====================================================
            #  调用 DeepSeek（分流式 / 非流式）
            # ====================================================
            if self.stream:
                result = self._call_llm_streaming(r, stream_callback)
                content = result["content"]
                tool_calls = result["tool_calls"]
                finish = result["finish_reason"]
            else:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=self.messages,
                    tools=TOOL_DEFINITIONS,
                    temperature=config.TEMPERATURE,
                    max_tokens=config.MAX_TOKENS,
                )
                choice = response.choices[0]
                msg = choice.message
                finish = choice.finish_reason

                # ---- 记录 LLM 原始输出 ----
                self.logger.llm_raw_output(r, msg)

                # Token 统计
                if hasattr(response, "usage") and response.usage:
                    self._total_tokens += response.usage.total_tokens

                content = msg.content or ""
                tool_calls = msg.tool_calls

            # ========================================================
            # 情况 1: 模型要调用工具
            # ========================================================
            if tool_calls:
                if self.stream:
                    # 流式模式下 tool_calls 已经是 dict 列表，需要转换为
                    # messages 可存储的格式
                    tc_for_history = []
                    for tc in tool_calls:
                        tc_for_history.append({
                            "id": tc["id"],
                            "type": tc.get("type", "function"),
                            "function": {
                                "name": tc["function"]["name"],
                                "arguments": tc["function"]["arguments"],
                            },
                        })
                    assistant_record = {
                        "role": "assistant",
                        "content": content,
                        "tool_calls": tc_for_history,
                    }
                    self.messages.append(assistant_record)

                    for tc in tool_calls:
                        tool_name = tc["function"]["name"]
                        try:
                            tool_args = json.loads(tc["function"]["arguments"])
                        except json.JSONDecodeError:
                            tool_args = {"raw": tc["function"]["arguments"]}

                        print(f"  [🔧 调用工具: {tool_name}]", flush=True)
                        if stream_callback:
                            stream_callback("tool_call", {
                                "name": tool_name,
                                "arguments": tc["function"]["arguments"],
                            })

                        # 构造一个伪 tool_call 对象供 _execute_tool 使用
                        result = self._execute_tool_dict(tc)

                        self.logger.tool_execution(
                            r, tool_name, tool_args, result
                        )
                        # 终端：输出工具结果摘要
                        preview = result[:200] + ('...' if len(result) > 200 else '')
                        print(f"  [✓ 结果] {preview}", flush=True)
                        if stream_callback:
                            stream_callback("tool_result", {
                                "name": tool_name,
                                "result": result,
                            })

                        self.messages.append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": result,
                        })
                else:
                    # 非流式：使用原有逻辑
                    assistant_record = self._dump_message_for_history(msg)
                    self.messages.append(assistant_record)

                    for tc in msg.tool_calls:
                        tool_name = tc.function.name
                        try:
                            tool_args = json.loads(tc.function.arguments)
                        except json.JSONDecodeError:
                            tool_args = {"raw": tc.function.arguments}

                        print(f"  [🔧 调用工具: {tool_name}]", flush=True)
                        if stream_callback:
                            stream_callback("tool_call", {
                                "name": tool_name,
                                "arguments": tc.function.arguments,
                            })

                        result = self._execute_tool(tc)

                        self.logger.tool_execution(
                            r, tool_name, tool_args, result
                        )
                        # 终端：输出工具结果摘要
                        preview = result[:200] + ('...' if len(result) > 200 else '')
                        print(f"  [✓ 结果] {preview}", flush=True)
                        if stream_callback:
                            stream_callback("tool_result", {
                                "name": tool_name,
                                "result": result,
                            })

                        self.messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": result,
                        })

                # ---- 记录本轮结束后的 context ----
                self.logger.context_snapshot(r, self.messages)
                continue

            # ========================================================
            # 情况 2: 模型无 tool_calls —— 需结合 finish_reason 判断
            # ========================================================
            if finish == "stop":
                final_text = content or ""
                self.messages.append({"role": "assistant", "content": final_text})
                self.logger.context_snapshot(r, self.messages)
                self.logger.final_output(final_text)
                if stream_callback:
                    stream_callback("done", {"text": final_text})
                # 同步输出到终端（流式/非流式均输出）
                if final_text:
                    print(f"\n🤖 Agent:\n{final_text}\n")
                else:
                    print("\n🤖 Agent: (无文本输出)\n")
                return final_text

            elif finish == "length":
                partial = content or ""
                self.messages.append({"role": "assistant", "content": partial})
                self.messages.append({
                    "role": "user",
                    "content": "（你的上一条回复被截断了，请继续完成。）"
                })
                self.logger.note(
                    f"finish_reason=length，输出被截断。"
                    f"已追加 continue 提示，进入下一轮。"
                )
                self.logger.context_snapshot(r, self.messages)
                print(f"  [⚠ 输出被截断，请求模型继续...]", flush=True)
                continue

            elif finish == "content_filter":
                fallback = "（回复被内容安全过滤器拦截，请换一种方式提问。）"
                self.messages.append({"role": "assistant", "content": fallback})
                self.logger.context_snapshot(r, self.messages)
                self.logger.final_output(fallback)
                self.logger.note("finish_reason=content_filter，内容被安全过滤。")
                if stream_callback:
                    stream_callback("error", {"message": fallback})
                print(f"\n🤖 Agent: {fallback}\n")
                return fallback

            else:
                final_text = content or ""
                self.messages.append({"role": "assistant", "content": final_text})
                self.logger.context_snapshot(r, self.messages)
                self.logger.final_output(final_text)
                self.logger.note(f"未知 finish_reason={finish}，按文本回复处理。")
                if stream_callback:
                    stream_callback("done", {"text": final_text})
                # 同步输出到终端（流式/非流式均输出）
                if final_text:
                    print(f"\n🤖 Agent:\n{final_text}\n")
                else:
                    print("\n🤖 Agent: (无文本输出)\n")
                return final_text

        # 超出最大轮次
        self.logger.max_rounds_exceeded(config.MAX_TOOL_ROUNDS)
        self.logger.context_snapshot(self._global_round, self.messages)

        fallback = "已达到最大工具调用轮次，请简化你的请求。"
        self.messages.append({"role": "assistant", "content": fallback})
        self.logger.final_output(fallback)
        if stream_callback:
            stream_callback("error", {"message": fallback})
        print(f"\n🤖 Agent: {fallback}\n")
        return fallback

    @property
    def total_tokens(self) -> int:
        """本次会话累计消耗 tokens。"""
        return self._total_tokens

    @property
    def context_tokens(self) -> int:
        """估算当前上下文 tokens（字符数 / 4）。"""
        chars = sum(len(str(m.get("content", ""))) for m in self.messages)
        return max(1, chars // 4)

    @property
    def max_context(self) -> int:
        """模型最大上下文窗口。"""
        return {
            "deepseek-v4-pro": 131072,
            "deepseek-v4-flash": 131072,
        }.get(self.model, 131072)

    def reset(self):
        """重置对话历史，仅保留系统提示词。"""
        self.messages = [{"role": "system", "content": self.system_prompt}]
        self._total_tokens = 0
        self.logger.reset()
        print("[对话已重置]")
