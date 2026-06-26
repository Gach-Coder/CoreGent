"""
MCP 客户端模块 —— 通过 stdio 连接 MCP 服务器，发现工具并转发调用。

支持:
  - 多服务器连接（config.MCP_SERVERS 列表）
  - 工具名前缀（避免与内置工具重名，默认 "mcp_"）
  - OpenAI 兼容的工具定义格式转换
  - 异步桥接（后台事件循环线程）

用法:
    manager = MCPClientManager()
    manager.connect_all()            # 连接所有配置的 MCP 服务器
    defs = manager.get_openai_tools()  # 获取 OpenAI 格式的工具定义
    result = manager.call_tool("mcp_read_file", {"path": "notes.txt"})
    manager.disconnect_all()
"""

import asyncio
import json
import threading
import time
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import Tool as MCPTool, TextContent

import config


# ============================================================
# 单服务器连接
# ============================================================

class MCPServerConnection:
    """与单个 MCP 服务器的 stdio 连接。"""

    def __init__(self, name: str, command: str, args: list[str]):
        """
        Args:
            name: 服务器名称（用作工具名前缀段）。
            command: 启动命令，如 "python"、"npx"。
            args: 命令行参数列表。
        """
        self.name = name
        self.command = command
        self.args = args
        self._server_params = StdioServerParameters(
            command=command,
            args=args,
        )
        self._tools: list[MCPTool] = []
        self._session: ClientSession | None = None
        self._stdio_ctx = None
        self._session_ctx = None
        self._connected = False
        self._error: str | None = None

    # ---- 属性 ----

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def tools(self) -> list[MCPTool]:
        return self._tools

    @property
    def error(self) -> str | None:
        return self._error

    # ---- 连接 / 断开 ----

    async def connect(self) -> None:
        """建立 stdio 连接，初始化会话，发现工具。"""
        try:
            self._stdio_ctx = stdio_client(self._server_params)
            self._read, self._write = await asyncio.wait_for(
                self._stdio_ctx.__aenter__(),
                timeout=config.MCP_CONNECT_TIMEOUT,
            )
            self._session_ctx = ClientSession(self._read, self._write)
            self._session = await asyncio.wait_for(
                self._session_ctx.__aenter__(),
                timeout=config.MCP_CONNECT_TIMEOUT,
            )
            await asyncio.wait_for(
                self._session.initialize(),
                timeout=config.MCP_CONNECT_TIMEOUT,
            )
            tools_result = await asyncio.wait_for(
                self._session.list_tools(),
                timeout=config.MCP_CONNECT_TIMEOUT,
            )
            self._tools = list(tools_result.tools) if tools_result.tools else []
            self._connected = True
            self._error = None
        except asyncio.TimeoutError:
            self._error = f"连接 MCP 服务器 '{self.name}' 超时"
            self._connected = False
        except Exception as e:
            self._error = f"连接 MCP 服务器 '{self.name}' 失败: {e}"
            self._connected = False

    async def disconnect(self) -> None:
        """关闭会话和 stdio 连接。"""
        try:
            if self._session_ctx is not None:
                await self._session_ctx.__aexit__(None, None, None)
                self._session_ctx = None
                self._session = None
        except Exception:
            pass
        try:
            if self._stdio_ctx is not None:
                await self._stdio_ctx.__aexit__(None, None, None)
                self._stdio_ctx = None
        except Exception:
            pass
        self._connected = False

    async def call_tool_async(self, name: str, arguments: dict[str, Any]) -> str:
        """异步调用 MCP 工具并返回文本结果。

        Args:
            name: MCP 工具名（不含前缀，即服务端原始名称）。
            arguments: 工具参数字典。

        Returns:
            工具执行结果的文本。
        """
        if not self._connected or self._session is None:
            return f"错误: MCP 服务器 '{self.name}' 未连接"

        try:
            result = await asyncio.wait_for(
                self._session.call_tool(name, arguments),
                timeout=config.MCP_CONNECT_TIMEOUT,
            )
            # 将 ContentBlock 列表转为字符串
            parts: list[str] = []
            for block in result.content:
                if hasattr(block, "text"):
                    parts.append(block.text)
                else:
                    parts.append(str(block))
            return "\n".join(parts) if parts else "(工具无输出)"
        except asyncio.TimeoutError:
            return f"错误: 调用 MCP 工具 '{name}' 超时"
        except Exception as e:
            return f"错误: 调用 MCP 工具 '{name}' 失败: {e}"

    # ---- 工具定义转换 ----

    def to_openai_definitions(self, prefix: str = "mcp_") -> list[dict[str, Any]]:
        """将 MCP 工具定义转为 OpenAI function calling 格式。

        Args:
            prefix: 添加到工具名的前缀，用于区分来自不同服务器的同名工具。

        Returns:
            OpenAI 兼容的工具定义列表。
        """
        definitions: list[dict[str, Any]] = []
        for tool in self._tools:
            defs: list[dict[str, Any]] = []
            # 构建 OpenAI function 描述
            func_def: dict[str, Any] = {
                "type": "function",
                "function": {
                    "name": f"{prefix}{tool.name}",
                    "description": (
                        f"[MCP:{self.name}] {tool.description or ''}"
                    ),
                    "parameters": tool.inputSchema if tool.inputSchema else {
                        "type": "object",
                        "properties": {},
                    },
                },
            }
            definitions.append(func_def)
        return definitions


# ============================================================
# MCP 客户端管理器
# ============================================================

class MCPClientManager:
    """管理多个 MCP 服务器连接，提供统一的工具发现和调用接口。

    内部使用后台线程运行 asyncio 事件循环，对外暴露同步接口。
    """

    def __init__(self, servers_config: list[dict] | None = None):
        """
        Args:
            servers_config: 服务器配置列表，默认从 config.MCP_SERVERS 读取。
        """
        self._servers_config = servers_config or config.MCP_SERVERS
        self._connections: dict[str, MCPServerConnection] = {}
        self._prefix = config.MCP_TOOL_PREFIX

        # 后台事件循环
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None

        self._all_tools: list[MCPTool] = []
        self._tool_map: dict[str, tuple[str, MCPTool]] = {}
        # _tool_map: prefixed_name → (server_name, MCPTool)

    # ---- 属性 ----

    @property
    def tool_count(self) -> int:
        return len(self._tool_map)

    @property
    def server_count(self) -> int:
        return len(self._connections)

    @property
    def connected_servers(self) -> list[str]:
        return [
            name for name, conn in self._connections.items()
            if conn.connected
        ]

    @property
    def errors(self) -> dict[str, str]:
        return {
            name: conn.error
            for name, conn in self._connections.items()
            if conn.error
        }

    # ---- 事件循环管理 ----

    def _start_loop(self) -> None:
        """启动后台事件循环线程。"""
        if self._loop is not None:
            return
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._loop.run_forever,
            daemon=True,
        )
        self._thread.start()

    def _stop_loop(self) -> None:
        """停止后台事件循环线程。"""
        if self._loop is None:
            return
        self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread is not None:
            self._thread.join(timeout=5.0)
        self._loop.close()
        self._loop = None
        self._thread = None

    def _run_async(self, coro) -> Any:
        """在后台事件循环中运行协程并返回结果。"""
        if self._loop is None:
            raise RuntimeError("MCP 事件循环未启动")
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=config.MCP_CONNECT_TIMEOUT + 5)

    # ---- 连接管理 ----

    def connect_all(self) -> bool:
        """连接所有配置的 MCP 服务器。

        Returns:
            是否至少有一台服务器连接成功。
        """
        if not config.MCP_ENABLED:
            return False

        self._start_loop()

        success_count = 0
        for srv_cfg in self._servers_config:
            name = srv_cfg["name"]
            conn = MCPServerConnection(
                name=name,
                command=srv_cfg["command"],
                args=srv_cfg.get("args", []),
            )
            self._connections[name] = conn

            try:
                self._run_async(conn.connect())
            except Exception as e:
                conn._error = f"连接异常: {e}"
                conn._connected = False

            if conn.connected:
                success_count += 1
                # 注册工具
                for tool in conn.tools:
                    prefixed = f"{self._prefix}{tool.name}"
                    self._tool_map[prefixed] = (name, tool)
                self._all_tools.extend(conn.tools)
            else:
                print(f"  [⚠ MCP] {conn.error}", flush=True)

        if success_count > 0:
            print(
                f"  [✓ MCP] 已连接 {success_count}/{len(self._servers_config)} "
                f"台服务器，共 {len(self._tool_map)} 个工具",
                flush=True,
            )
        return success_count > 0

    def disconnect_all(self) -> None:
        """断开所有 MCP 服务器连接。"""
        for conn in self._connections.values():
            try:
                self._run_async(conn.disconnect())
            except Exception:
                pass
        self._connections.clear()
        self._tool_map.clear()
        self._all_tools.clear()
        self._stop_loop()

    # ---- 工具定义 ----

    def get_openai_definitions(self) -> list[dict[str, Any]]:
        """获取所有 MCP 工具的 OpenAI 兼容定义。

        Returns:
            OpenAI function calling 格式的工具定义列表。
        """
        definitions: list[dict[str, Any]] = []
        for prefixed_name, (srv_name, tool) in self._tool_map.items():
            func_def: dict[str, Any] = {
                "type": "function",
                "function": {
                    "name": prefixed_name,
                    "description": (
                        f"[MCP:{srv_name}] {tool.description or ''}"
                    ),
                    "parameters": tool.inputSchema if tool.inputSchema else {
                        "type": "object",
                        "properties": {},
                    },
                },
            }
            definitions.append(func_def)
        return definitions

    # ---- 工具调用 ----

    def call_tool(self, prefixed_name: str, arguments: dict[str, Any]) -> str:
        """同步调用 MCP 工具。

        Args:
            prefixed_name: 带前缀的工具名，如 "mcp_read_file"。
            arguments: 工具参数字典。

        Returns:
            工具执行结果文本。
        """
        if prefixed_name not in self._tool_map:
            return f"错误: 未知 MCP 工具 '{prefixed_name}'"

        srv_name, tool = self._tool_map[prefixed_name]
        conn = self._connections.get(srv_name)
        if conn is None or not conn.connected:
            return f"错误: MCP 服务器 '{srv_name}' 未连接"

        try:
            return self._run_async(
                conn.call_tool_async(tool.name, arguments)
            )
        except Exception as e:
            return f"错误: MCP 工具调用异常: {e}"
