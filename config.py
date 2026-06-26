"""
配置模块 —— 管理 DeepSeek API 的连接参数、模型选择与日志行为。

所有配置项均可通过环境变量覆盖，方便在不同环境下部署。
"""

import os

# ---- API 连接 ----
API_KEY = os.environ.get("DEEPSEEK_API_KEY")
BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

# ---- 模型选择 ----
# deepseek-v4-pro  : 旗舰模型，推理能力最强
# deepseek-v4-flash: 轻量模型，速度快、成本低
MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")

# ---- 推理参数 ----
TEMPERATURE = float(os.environ.get("AGENT_TEMPERATURE", "0.0"))
MAX_TOKENS = int(os.environ.get("AGENT_MAX_TOKENS", "40960"))

# ---- 智能体循环 ----
MAX_TOOL_ROUNDS = int(os.environ.get("AGENT_MAX_TOOL_ROUNDS", "100"))

# ---- 流式输出 ----
STREAM = os.environ.get("AGENT_STREAM", "1") == "1"  # 设为 0 可关闭流式输出

# ---- 日志 ----
LOG_PATH = os.environ.get("AGENT_LOG_PATH", "log.txt")
LOG_ECHO = os.environ.get("AGENT_LOG_ECHO", "0") == "1"  # 设为 1 可同步输出到终端

# ---- 网络工具 ----
WEB_TIMEOUT = int(os.environ.get("AGENT_WEB_TIMEOUT", "30"))
WEB_RETRIES = int(os.environ.get("AGENT_WEB_RETRIES", "3"))
HTTP_PROXY = os.environ.get("AGENT_HTTP_PROXY") or os.environ.get("HTTP_PROXY") or ""
HTTPS_PROXY = os.environ.get("AGENT_HTTPS_PROXY") or os.environ.get("HTTPS_PROXY") or ""

DEBUG_FLAG = True

# ---- MCP 连接 ----
# MCP 服务器配置列表，每项包含:
#   name    : 服务器名称（工具名前缀，如 "mcp_filesystem"）
#   command : 启动命令（python / npx 等）
#   args    : 命令行参数列表
_PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

MCP_SERVERS = [
    {
        "name": "mcp_filesystem",
        "command": "python",
        "args": [os.path.join(_PROJECT_DIR, "MCP", "server.py")],
    },
]

# MCP 工具名前缀（避免与内置工具重名）
MCP_TOOL_PREFIX = os.environ.get("AGENT_MCP_TOOL_PREFIX", "mcp_")

# MCP 连接超时（秒）
MCP_CONNECT_TIMEOUT = int(os.environ.get("AGENT_MCP_CONNECT_TIMEOUT", "10"))

# 是否启用 MCP（设为 0 可完全禁用）
MCP_ENABLED = os.environ.get("AGENT_MCP_ENABLED", "1") == "1"
