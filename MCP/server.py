"""
MCP File Server — 文件系统操作 MCP 服务器
运行方式:
    python server.py
或者通过 MCP 客户端配置:
    {
        "mcpServers": {
            "filesystem": {
                "command": "python",
                "args": ["D:\\DATA\\PythonProj\\MCP\\server.py"]
            }
        }
    }
"""

import json
import asyncio
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    Tool,
    TextContent,
)

# ── 服务器配置 ──────────────────────────────────────────
SERVER_NAME = "mcp-filesystem"
ROOT_DIR = Path(__file__).parent.resolve()

# 确保根目录存在
ROOT_DIR.mkdir(parents=True, exist_ok=True)

# ── 创建 MCP Server 实例 ─────────────────────────────────
server = Server(SERVER_NAME)


# ── 路径安全校验 ─────────────────────────────────────────
def safe_path(requested: str) -> Path:
    """将请求路径解析到 ROOT_DIR 内，防止目录穿越攻击。"""
    p = (ROOT_DIR / requested).resolve()
    if not str(p).startswith(str(ROOT_DIR)):
        raise ValueError(f"路径越界: {requested}")
    return p


# ── 工具列表 ─────────────────────────────────────────────
@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="write_file",
            description="将内容写入指定文件。会创建不存在的父目录。",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "相对于根目录的文件路径，例如 'subdir/notes.txt'",
                    },
                    "content": {
                        "type": "string",
                        "description": "要写入的文本内容",
                    },
                },
                "required": ["path", "content"],
            },
        ),
        Tool(
            name="read_file",
            description="读取指定文件的内容。",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "相对于根目录的文件路径",
                    },
                },
                "required": ["path"],
            },
        ),
        Tool(
            name="list_directory",
            description="列出目录中的文件和子目录。",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "相对于根目录的目录路径，留空表示根目录",
                    },
                },
            },
        ),
        Tool(
            name="delete_file",
            description="删除指定的文件。",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "相对于根目录的文件路径",
                    },
                },
                "required": ["path"],
            },
        ),
        Tool(
            name="get_file_info",
            description="获取文件的元信息（大小、修改时间等）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "相对于根目录的文件路径",
                    },
                },
                "required": ["path"],
            },
        ),
        Tool(
            name="Pet_Hajimi",
            description="摸一摸哈基米",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "相对于根目录的文件路径",
                    },
                },
                "required": ["path"],
            },
        ),
    ]


# ── 工具调用处理 ─────────────────────────────────────────
@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    try:
        if name == "write_file":
            target = safe_path(arguments["path"])
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(arguments["content"], encoding="utf-8")
            size = target.stat().st_size
            return [TextContent(type="text", text=f"✅ 写入成功: {target}\n大小: {size} 字节")]

        elif name == "read_file":
            target = safe_path(arguments["path"])
            if not target.exists():
                return [TextContent(type="text", text=f"❌ 文件不存在: {arguments['path']}")]
            content = target.read_text(encoding="utf-8")
            return [TextContent(type="text", text=content)]

        elif name == "list_directory":
            target = safe_path(arguments.get("path", ""))
            if not target.exists():
                return [TextContent(type="text", text=f"❌ 目录不存在: {arguments.get('path', '')}")]
            if not target.is_dir():
                return [TextContent(type="text", text=f"❌ 不是目录: {arguments.get('path', '')}")]
            entries = []
            for entry in sorted(target.iterdir()):
                suffix = "/" if entry.is_dir() else ""
                entries.append(f"  {entry.name}{suffix}")
            header = f"📁 {target}/  ({len(entries)} 项)"
            return [TextContent(type="text", text=header + "\n" + "\n".join(entries))]

        elif name == "delete_file":
            target = safe_path(arguments["path"])
            if not target.exists():
                return [TextContent(type="text", text=f"❌ 文件不存在: {arguments['path']}")]
            target.unlink()
            return [TextContent(type="text", text=f"✅ 已删除: {arguments['path']}")]

        elif name == "get_file_info":
            target = safe_path(arguments["path"])
            if not target.exists():
                return [TextContent(type="text", text=f"❌ 文件不存在: {arguments['path']}")]
            stat = target.stat()
            info = {
                "path": str(target),
                "size": stat.st_size,
                "is_dir": target.is_dir(),
                "modified": target.stat().st_mtime,
            }
            return [TextContent(type="text", text=json.dumps(info, indent=2, ensure_ascii=False))]
        elif name == "Pet_Hajimi":
            return [TextContent(type="text", text=f"哈基米变得更开心了。")] 
        else:
            return [TextContent(type="text", text=f"❌ 未知工具: {name}")]

    except ValueError as e:
        return [TextContent(type="text", text=f"❌ 路径错误: {e}")]
    except Exception as e:
        return [TextContent(type="text", text=f"❌ 服务器错误: {e}")]


# ── 入口 ─────────────────────────────────────────────────
async def main():
    async with stdio_server() as (reader, writer):
        await server.run(reader, writer, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
