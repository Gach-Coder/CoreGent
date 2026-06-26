"""
工具模块 —— 定义 Agent 可调用的工具及其 OpenAI 兼容的函数描述。

每添加一个工具需要两步：
  1. 在 TOOL_DEFINITIONS 中添加函数描述（供模型识别）
  2. 在 TOOL_MAP 中注册对应的 Python 实现函数

工具实现统一签名为:  func(**kwargs) -> str
"""

import os
import re
import time
import subprocess
import glob as glob_mod
import urllib.request
import urllib.parse
import urllib.error
import ssl
from html import unescape
from typing import Any

import config
from config import DEBUG_FLAG

# ---- SearchTool 集成 ----
import sys
_SEARCHTOOL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "SearchTool")
sys.path.insert(0, _SEARCHTOOL_DIR)
from search_tool import SearchTool

_search_tool = SearchTool()  # 单例，自动轮换引擎 / UA

# ============================================================
# 工具实现 —— 纯 Python 函数，供 Agent 执行时调用
# ============================================================

def _run_shell_command(command: str, timeout: int = 30) -> str:
    """执行一条 shell 命令并返回 stdout+stderr（合并输出）。

    Args:
        command: 要执行的 shell 命令。
        timeout: 超时秒数，默认 30。

    Returns:
        命令的标准输出 + 标准错误（合并）。
    """
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=os.getcwd(),
        )
        out = result.stdout.strip()
        err = result.stderr.strip()
        parts = []
        if out:
            parts.append(out)
        if err:
            parts.append(f"[stderr]\n{err}")
        if not parts:
            parts.append(f"(exit code {result.returncode})")
        return "\n".join(parts)
    except subprocess.TimeoutExpired:
        return f"错误: 命令超时（>{timeout}s）: {command}"


def _read_file(filepath: str, max_lines: int = 200) -> str:
    """读取文件内容。

    Args:
        filepath: 文件路径（相对或绝对）。
        max_lines: 最多返回的行数，默认 200。

    Returns:
        文件内容，或错误信息。
    """
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        total = len(lines)
        if total > max_lines:
            lines = lines[:max_lines]
            return f"(文件共 {total} 行，仅显示前 {max_lines} 行)\n\n" + "".join(lines)
        return "".join(lines)
    except FileNotFoundError:
        return f"错误: 文件不存在: {filepath}"
    except IsADirectoryError:
        return f"错误: 路径是目录而非文件: {filepath}"
    except PermissionError:
        return f"错误: 没有权限读取: {filepath}"
    except Exception as e:
        return f"错误: 读取失败: {e}"


def _write_file(filepath: str, content: str) -> str:
    """将内容写入文件（覆盖模式）。

    Args:
        filepath: 目标文件路径。
        content: 要写入的文本内容。

    Returns:
        操作结果。
    """
    try:
        # 确保父目录存在
        parent = os.path.dirname(filepath)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return f"写入成功: {filepath} ({len(content)} 字符)"
    except Exception as e:
        return f"错误: 写入失败: {e}"


def _list_directory(dirpath: str = ".") -> str:
    """列出目录中的文件和子目录。

    Args:
        dirpath: 目标目录路径，默认当前目录。

    Returns:
        换行分隔的目录内容列表。
    """
    try:
        entries = os.listdir(dirpath)
        if not entries:
            return f"目录为空: {dirpath}"
        lines = []
        for name in sorted(entries):
            full = os.path.join(dirpath, name)
            marker = "/" if os.path.isdir(full) else ""
            lines.append(f"  {name}{marker}")
        return f"目录 {os.path.abspath(dirpath)} 的内容:\n" + "\n".join(lines)
    except FileNotFoundError:
        return f"错误: 目录不存在: {dirpath}"
    except PermissionError:
        return f"错误: 没有权限访问: {dirpath}"
    except Exception as e:
        return f"错误: 列出目录失败: {e}"


def _search_files(pattern: str, recursive: bool = True) -> str:
    """按 glob 模式搜索文件。

    Args:
        pattern: glob 模式，如 "*.py" 或 "src/**/*.ts"。
        recursive: 是否递归搜索，默认 True。

    Returns:
        换行分隔的匹配文件列表。
    """
    try:
        matches = glob_mod.glob(pattern, recursive=recursive)
        if not matches:
            return f"未找到匹配 '{pattern}' 的文件。"
        # 限制返回数量
        if len(matches) > 100:
            return "\n".join(matches[:100]) + f"\n\n... 共 {len(matches)} 个匹配，仅显示前 100 个。"
        return "\n".join(matches)
    except Exception as e:
        return f"错误: 搜索失败: {e}"


# ---- HTTP 请求助手 ----

# 按优先级尝试的 User-Agent 列表（重试时轮换）
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

# 构建带代理的 opener（全局复用）
_proxy_handler = None
_opener = None


def _get_opener():
    """延迟构建带代理的 urllib opener。"""
    global _proxy_handler, _opener
    if _opener is not None:
        return _opener

    handlers = []
    proxy_url = None

    # HTTPS 代理优先，其次 HTTP 代理
    if config.HTTPS_PROXY:
        proxy_url = config.HTTPS_PROXY
    elif config.HTTP_PROXY:
        proxy_url = config.HTTP_PROXY

    if proxy_url:
        _proxy_handler = urllib.request.ProxyHandler({
            "http": proxy_url,
            "https": proxy_url,
        })
        handlers.append(_proxy_handler)

    # SSL 上下文：跳过证书验证（仅用于代理/内网环境）
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE
    https_handler = urllib.request.HTTPSHandler(context=ssl_ctx)
    handlers.append(https_handler)

    _opener = urllib.request.build_opener(*handlers)
    return _opener


def _http_request(
    url: str,
    data: bytes | None = None,
    headers: dict | None = None,
    method: str = "GET",
) -> bytes:
    """带重试、代理、超时控制的 HTTP 请求。

    自动重试 config.WEB_RETRIES 次，指数退避。
    每次重试时轮换 User-Agent。
    超时时间来自 config.WEB_TIMEOUT。

    Args:
        url: 请求 URL。
        data: POST 请求体（None 则为 GET）。
        headers: 额外的请求头。
        method: HTTP 方法。

    Returns:
        响应体字节。

    Raises:
        urllib.error.URLError: 所有重试耗尽后仍失败。
    """
    base_headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate",
    }
    if headers:
        base_headers.update(headers)

    opener = _get_opener()
    max_retries = config.WEB_RETRIES
    timeout = config.WEB_TIMEOUT
    last_error = None

    for attempt in range(max_retries):
        ua = _USER_AGENTS[attempt % len(_USER_AGENTS)]
        base_headers["User-Agent"] = ua

        req = urllib.request.Request(url, data=data, headers=base_headers)
        if method != "GET" and method != "POST":
            req.method = method

        try:
            with opener.open(req, timeout=timeout) as resp:
                # 用 gzip 解压
                raw = resp.read()
                return raw
        except urllib.error.HTTPError as e:
            last_error = e
            # 4xx 不重试（客户端错误）
            if 400 <= e.code < 500:
                raise
        except urllib.error.URLError as e:
            last_error = e
        except Exception as e:
            last_error = e

        # 指数退避
        if attempt < max_retries - 1:
            delay = 2 ** attempt
            time.sleep(delay)

    raise last_error  # type: ignore[misc]


def _web_search(query: str, max_results: int = 5) -> str:
    """使用多引擎搜索网页（百度/Bing/搜狗自动轮换），返回标题、链接和摘要。

    自动随机轮换搜索引擎和 User-Agent，降低单引擎封禁风险。
    内置失败重试：首引擎失败自动切换下一个。

    Args:
        query: 搜索关键词。
        max_results: 最多返回的结果数，默认 5。

    Returns:
        格式化的搜索结果文本。
    """
    try:
        print("_search_tool.web_search(query=%s, max_results=%d)"%(query,max_results))
        return _search_tool.web_search(query, max_results=max_results)
    except Exception as e:
        return f"错误: 搜索异常: {e}"


# （旧 _web_search_bing 已删除，由 SearchTool 替代）


# （旧 _format_search_results 已删除，格式化由 SearchTool 内部完成）


def _web_fetch(url: str, max_chars: int = 5000) -> str:
    """获取指定 URL 的文本内容（剥离 HTML 标签）。

    内置重试（{WEB_RETRIES}次）和代理支持。

    Args:
        url: 目标网页 URL（须以 http:// 或 https:// 开头）。
        max_chars: 最多返回的字符数，默认 5000。

    Returns:
        网页的纯文本内容（截断至 max_chars），含排障提示。
    """.replace("{WEB_RETRIES}", str(config.WEB_RETRIES))
    try:
        if not url.startswith(("http://", "https://")):
            return f"错误: URL 必须以 http:// 或 https:// 开头: {url}"

        raw = _http_request(url)

        # 从 Content-Type 推断编码（近似：取 opener 最后一个 response）
        encoding = "utf-8"
        try:
            html = raw.decode(encoding, errors="replace")
        except (LookupError, UnicodeDecodeError):
            html = raw.decode("utf-8", errors="replace")

        # 剥离 HTML 标签和脚本/样式
        text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]*>", " ", text)
        text = unescape(text)

        # 压缩空白
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = text.strip()

        if len(text) > max_chars:
            text = text[:max_chars] + f"\n\n... (内容已截断，共 {len(text)} 字符)"

        return text if text else "(页面无可见文本内容)"

    except urllib.error.HTTPError as e:
        return f"错误: 请求被拒绝 (HTTP {e.code}): {url}"
    except urllib.error.URLError as e:
        return _format_network_error(e, "获取网页")
    except Exception as e:
        return f"错误: 获取网页失败: {e}"


def _format_network_error(error: urllib.error.URLError, operation: str) -> str:
    """将网络错误格式化为带排障提示的消息。

    Args:
        error: urllib 异常对象。
        operation: 操作名称（如 "搜索"、"获取网页"）。

    Returns:
        格式化的错误消息。
    """
    reason = str(error.reason)

    tips = []
    if "timed out" in reason.lower():
        tips = [
            f"错误: {operation}超时 (已重试 {config.WEB_RETRIES} 次)。",
            "",
            "可能的原因和解决方案:",
            "  1. 网络不通 —— 检查是否能访问外网: ping www.bing.com",
            "  2. 需要代理 —— 设置环境变量:",
            "     set AGENT_HTTP_PROXY=http://127.0.0.1:7890",
            "     或  set HTTPS_PROXY=http://127.0.0.1:7890",
            "  3. 超时太短 —— 增大超时:",
            "     set AGENT_WEB_TIMEOUT=60",
        ]
    elif "refused" in reason.lower() or "reset" in reason.lower():
        tips = [
            f"错误: {operation}连接被拒绝 ({reason})。",
            "通常是代理配置问题，检查 AGENT_HTTP_PROXY 是否正确。",
        ]
    elif "getaddrinfo" in reason.lower() or "nodename" in reason.lower():
        tips = [
            f"错误: DNS 解析失败 ({reason})。",
            "请检查:",
            "  1. 网络是否连通",
            "  2. DNS 服务器是否正常 (可尝试 nslookup www.bing.com)",
            "  3. 如果使用了代理，代理是否配置了 DNS 转发",
        ]
    else:
        tips = [
            f"错误: {operation}网络连接失败: {reason}",
            f"已重试 {config.WEB_RETRIES} 次，均失败。",
            f"当前超时: {config.WEB_TIMEOUT}s",
            f"代理: {'已设置' if config.HTTP_PROXY or config.HTTPS_PROXY else '未设置'}",
        ]

    return "\n".join(tips)


# ============================================================
# OpenAI 兼容的工具定义 —— 供 API 调用时传入 tools 参数
# ============================================================

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "run_shell_command",
            "description": (
                "执行一条 shell 命令并返回其标准输出和标准错误。"
                "适用于运行脚本、调用系统工具、编译代码、安装包等任何需要命令行操作的场景。"
                "注意: 不要执行破坏性命令（如 rm -rf）。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "要执行的 shell 命令，例如 'dir' 或 'python --version'。",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "超时秒数，默认 30。对于可能很慢的操作（如 pip install）建议设置更大的值。",
                    },
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取指定文件的内容。",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {
                        "type": "string",
                        "description": "要读取的文件路径，相对或绝对路径。",
                    },
                    "max_lines": {
                        "type": "integer",
                        "description": "最多返回的行数，默认 200。超过时仅返回前 N 行并附提示。",
                    },
                },
                "required": ["filepath"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "将文本内容写入文件。如果父目录不存在则自动创建。",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {
                        "type": "string",
                        "description": "目标文件路径。",
                    },
                    "content": {
                        "type": "string",
                        "description": "要写入的文本内容。",
                    },
                },
                "required": ["filepath", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "列出指定目录下的文件和子目录。",
            "parameters": {
                "type": "object",
                "properties": {
                    "dirpath": {
                        "type": "string",
                        "description": "要列出的目录路径，默认 '.'（当前目录）。",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_files",
            "description": "按 glob 模式搜索匹配的文件，支持通配符。",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "glob 搜索模式，如 '*.py'、'**/*.txt'、'src/**/*.js'。",
                    },
                    "recursive": {
                        "type": "boolean",
                        "description": "是否递归搜索子目录，默认 true。",
                    },
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "使用多引擎（百度/Bing/搜狗自动轮换）在互联网上搜索信息。"
                "返回搜索结果的标题、链接和摘要。适用于查询实时信息、"
                "新闻、百科知识、技术文档等任何需要联网获取的内容。"
                "自动轮换搜索引擎和User-Agent，降低封禁风险。"
                "注意: 搜索结果来自公开网络，不一定完全准确。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词，如 'Python 3.12 新特性' 或 '今天天气'。",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "最多返回的结果数，默认 5。",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": (
                "获取指定 URL 的网页内容，返回去除了 HTML 标签的纯文本。"
                "适用于提取搜索结果中某个具体页面的详细内容。"
                "注意: 页面内容会被截断到 5000 字符以内。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "目标网页的完整 URL，如 'https://docs.python.org/3/library/re.html'。",
                    },
                    "max_chars": {
                        "type": "integer",
                        "description": "最多返回的字符数，默认 5000。",
                    },
                },
                "required": ["url"],
            },
        },
    },
]

# ============================================================
# 工具调度映射 —— 函数名 → 实现函数
# ============================================================

TOOL_MAP: dict[str, Any] = {
    "run_shell_command": _run_shell_command,
    "read_file": _read_file,
    "write_file": _write_file,
    "list_directory": _list_directory,
    "search_files": _search_files,
    "web_search": _web_search,
    "web_fetch": _web_fetch,
}

# ---- MCP 集成的模块级备份 ----
# 保存内置定义的副本，用于 reset 后恢复
_BUILTIN_TOOL_DEFINITIONS = list(TOOL_DEFINITIONS)
_BUILTIN_TOOL_MAP = dict(TOOL_MAP)

# ---- MCP 工具注册 ----

# 由 register_mcp_tools() 设置，用于 Agent 中 tool_calls 分发
_mcp_manager: Any = None


def get_mcp_manager() -> Any:
    """获取当前的 MCPClientManager 实例（供 Agent 分发工具调用）。"""
    return _mcp_manager


def register_mcp_tools(manager: Any) -> int:
    """注册指定 MCPClientManager 的所有工具到全局 TOOL_DEFINITIONS / TOOL_MAP。

    将 MCP 工具以带前缀的名称注册（如 "mcp_read_file"），
    与内置工具（read_file）区分。

    可通过多次调用追加多个服务器的工具。

    Args:
        manager: MCPClientManager 实例。

    Returns:
        注册的工具数量。
    """
    global _mcp_manager
    _mcp_manager = manager

    mcp_defs = manager.get_openai_definitions()

    # 清理旧的 MCP 工具（按前缀识别）
    prefix = config.MCP_TOOL_PREFIX
    TOOL_DEFINITIONS[:] = [
        d for d in TOOL_DEFINITIONS
        if not d["function"]["name"].startswith(prefix)
    ]
    TOOL_MAP_keys_to_remove = [
        k for k in TOOL_MAP if k.startswith(prefix)
    ]
    for k in TOOL_MAP_keys_to_remove:
        del TOOL_MAP[k]

    # 添加 MCP 工具定义
    for mcp_def in mcp_defs:
        TOOL_DEFINITIONS.append(mcp_def)

        tool_name = mcp_def["function"]["name"]
        # 创建闭包捕获 tool_name
        def _make_mcp_caller(name: str):
            def _mcp_caller(**kwargs) -> str:
                mgr = get_mcp_manager()
                if mgr is None:
                    return f"错误: MCP 管理器未初始化，无法调用 '{name}'"
                return mgr.call_tool(name, kwargs)
            return _mcp_caller

        TOOL_MAP[tool_name] = _make_mcp_caller(tool_name)

    return len(mcp_defs)


def unregister_mcp_tools() -> None:
    """移除所有 MCP 工具，恢复内置工具列表。"""
    global _mcp_manager
    _mcp_manager = None
    TOOL_DEFINITIONS[:] = list(_BUILTIN_TOOL_DEFINITIONS)
    TOOL_MAP.clear()
    TOOL_MAP.update(_BUILTIN_TOOL_MAP)
