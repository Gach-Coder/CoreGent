# CoreGent

> 基于 DeepSeek 模型的命令行智能体 —— 用自然语言操作文件、执行命令、搜索网络。

## 特性

- **工具调用 (Tool Calling)** —— 多轮 ReAct 循环，模型自主选择工具、填入参数、根据结果继续推理
- **7 个内置工具** —— 文件读写、目录浏览、Shell 命令执行、文件搜索、网页搜索/抓取
- **MCP 协议集成** —— 通过 Model Context Protocol 连接外部工具服务器，即插即用扩展能力
- **Web UI** —— React 前端 + Flask/SSE 流式后端，支持思考过程展示、可折叠工具调用卡
- **全链路日志** —— 每次 LLM 输入/输出、工具执行、上下文快照均写入日志文件，方便调试审计
- **流式输出** —— 终端打字机效果，实时展示模型回复

## 架构

```
用户输入 (CLI / Web UI)
       │
       ▼
┌──────────────────────────────────┐
│  Agent (agent.py)                │
│  ReAct 循环:                     │
│    LLM ←→ 工具执行 ←→ 结果回传   │
│                                  │
│  ┌────────────┐  ┌────────────┐  │
│  │ 内置工具    │  │ MCP 工具    │  │
│  │ (tools.py) │  │ (mcp_*)    │  │
│  └────────────┘  └────────────┘  │
└──────────────────────────────────┘
       │
       ▼
  DeepSeek API
```

| 模块 | 职责 |
| --- | --- |
| `main.py` | CLI 交互入口，支持交互/单次两种模式 |
| `agent.py` | 核心 Agent，封装模型调用与工具执行循环 |
| `tools.py` | 7 个内置工具 + MCP 工具注册 |
| `mcp_client.py` | MCP 客户端，通过 stdio 连接外部工具服务器 |
| `logger.py` | 全链路日志，记录每一步 LLM/工具交互 |
| `web_ui.py` | Flask 后端，SSE 流式 + React 静态文件 |
| `web/` | React 前端 (Vite + useReducer) |
| `config.py` | 所有配置，均支持环境变量覆盖 |

## 内置工具

| 工具 | 功能 |
| --- | --- |
| `run_shell_command` | 执行 Shell 命令 |
| `read_file` | 读取文件内容 |
| `write_file` | 写入文件（自动创建父目录） |
| `list_directory` | 列出目录内容 |
| `search_files` | 按 glob 模式搜索文件 |
| `web_search` | 搜索引擎检索 |
| `web_fetch` | 抓取网页纯文本 |

## 快速开始

### 1. 安装依赖

```bash
# Python 依赖
pip install -r requirements.txt

# 前端依赖（仅 Web UI）
cd web && npm install
```

### 2. 设置 API Key

```bash
# Windows
set DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxx

# Linux / Mac
export DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxx
```

API Key 获取: [platform.deepseek.com/api_keys](https://platform.deepseek.com/api_keys)

### 3. 运行

```bash
# 交互模式
python main.py

# 单次模式
python main.py "列出当前目录的所有文件"

# 切换模型
set DEEPSEEK_MODEL=deepseek-v4-pro
python main.py
```

### 4. Web UI

```bash
# 构建前端（首次或代码更新后）
cd web && npm install && npm run build

# 启动服务
cd .. && python web_ui.py

# 浏览器访问 http://localhost:5003
```

## 配置

所有配置通过环境变量覆盖，主要项:

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DEEPSEEK_API_KEY` | (必填) | API 密钥 |
| `DEEPSEEK_MODEL` | `deepseek-v4-flash` | 模型选择 |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | API 端点（兼容 OpenAI 接口） |
| `AGENT_STREAM` | `1` | 流式输出开关 |
| `AGENT_MAX_TOOL_ROUNDS` | `100` | 最大工具调用轮次 |
| `AGENT_LOG_ECHO` | `0` | 设为 `1` 同步输出日志到终端 |
| `AGENT_MCP_ENABLED` | `1` | 设为 `0` 禁用 MCP |

完整配置项见 [config.py](config.py)。

## 示例

```
👤 You: 在当前目录创建一个 hello.py，内容是打印 Hello World
  🔧 write_file
🤖 Agent: 已在当前目录创建 hello.py。

👤 You: 运行一下这个文件
  🔧 run_shell_command
🤖 Agent: 执行输出 "Hello World"，运行正常。

👤 You: 搜索所有 .py 文件
  🔧 search_files
🤖 Agent: 找到 hello.py, main.py, agent.py ...

👤 You: Python 3.12 有什么新特性？
  🔧 web_search
🤖 Agent: 主要新特性包括：更灵活的 f-string (PEP 701)...
```

## 项目结构

```
CoreGent/
├── main.py              # CLI 入口
├── agent.py             # 核心 Agent
├── tools.py             # 内置工具 + MCP 注册
├── mcp_client.py        # MCP 客户端
├── logger.py            # 日志模块
├── web_ui.py            # Flask 后端
├── web/                 # React 前端
├── config.py            # 配置
├── MCP/                 # MCP 服务端
├── SearchTool/          # 搜索引擎模块
└── requirements.txt     # 依赖清单
```

## 依赖

- Python ≥ 3.10
- [openai](https://pypi.org/project/openai/) ≥ 1.0 — OpenAI 兼容 SDK
- [mcp](https://pypi.org/project/mcp/) ≥ 1.0 — Model Context Protocol SDK
- [flask](https://pypi.org/project/flask/) ≥ 3.0 — Web UI 后端
- Node.js (仅 Web UI) — React + Vite

## 许可

MIT
