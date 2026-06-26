# CoreGent —— 基于 DeepSeek 模型的命令行智能体

## 一、项目概述

这是一个基于 Python 构建的简单 AI 智能体 (Agent) 项目。它通过 OpenAI 兼容接口调用 DeepSeek 大语言模型，支持工具调用 (Tool Calling)，能够根据用户的自然语言请求自动选择并执行工具，完成文件操作、命令执行、目录浏览等任务。

**核心依赖:** `openai` (OpenAI Python SDK) + `mcp` (MCP Python SDK) + `flask` (Flask Web 框架) + `subprocess` (Python 标准库)

**亮点功能:**

- **完整的 log.txt 日志** —— 每一次 LLM 调用的输入/原始输出/工具执行全过程均写入文件，方便调试、审计和二次开发。
- **工具调用循环** —— 支持多轮 tool calling，模型可连续调用多个工具。
- **对话记忆** —— 保留完整消息链，支持多轮对话上下文。
- **MCP 集成** —— 通过 Model Context Protocol 连接外部工具服务器，自动发现并注册远程工具，扩展 Agent 的能力边界。
- **Web UI** —— React 前端 + Flask/SSE 后端，支持流式输出、思考过程展示、可折叠工具调用卡，在浏览器中与 Agent 交互。

**适用场景:**

- 用自然语言操作文件和目录（创建、读取、搜索）
- 让 AI 代为执行安全的 shell 命令
- 作为更复杂智能体项目的起点进行二次开发
- 调试/审计 Agent 行为 —— 通过 log.txt 回溯每一步决策

## 二、项目结构

```
CoreGent/
├── main.py              # 入口：交互式命令行界面 + 单次模式
├── agent.py             # 核心：Agent 类，封装模型调用与工具执行循环
├── tools.py             # 工具：定义内置工具 + MCP 工具注册
├── mcp_client.py        # MCP：通过 stdio 连接 MCP 服务器，发现并调用远程工具
├── logger.py            # 日志：将每一步 LLM/工具交互写入 log.txt
├── web_ui.py            # Web UI：Flask 后端（CORS + SSE + React 静态文件）
├── web/                 # React 前端
│   ├── package.json     #   npm 依赖 (react, vite)
│   ├── vite.config.js   #   Vite 配置（开发代理 → Flask）
│   ├── src/
│   │   ├── App.jsx      #     根组件：useReducer 状态管理
│   │   ├── App.css      #     暗色主题
│   │   ├── api.js       #     SSE/REST API 封装
│   │   └── components/  #     Header, ChatArea, MessageBubble,
│   │                    #     ToolCallCard, InputArea
│   └── dist/            #   生产构建产物（npm run build）
├── config.py            # 配置：API Key、模型选择、日志参数
├── requirements.txt     # Python 依赖清单
├── MCP/                 # MCP 服务端
├── SearchTool/          # 搜索工具
├── sessions/            # 会话存储
├── log.txt              # 运行日志（自动生成，追加写入）
└── README.md            # 本文件
```

## 三、各模块详细说明

### 3.1 main.py —— 交互入口

提供两种运行模式：

- **交互模式:** 直接运行 `python main.py`，进入命令行对话循环
- **单次模式:** `python main.py "你的请求"`，执行一次后退出

内置命令:

- `help`  - 显示帮助和示例
- `reset` - 重置对话历史
- `quit`  - 退出程序

### 3.2 agent.py —— 核心智能体

Agent 类实现标准的 ReAct 式工具调用循环:

```
用户输入
   │
   ▼
┌─────────────────────────────────────────────┐
│  1. 记录用户输入到 log.txt                    │
│  2. 记录完整 messages → log.txt (LLM INPUT)  │
│  3. 发送给 DeepSeek（附工具定义）              │
│  4. 记录模型原始返回 → log.txt (LLM RAW)      │
│  5. 模型返回:                                 │
│     ├── 有 tool_calls → 记录并执行工具         │
│     │   记录工具结果 → log.txt (TOOL EXEC)     │
│     │   记录 context 快照 → log.txt            │
│     │   结果回传 → 回到步骤 2                   │
│     └── 纯文本回复 → 记录最终输出 → 返回给用户   │
└─────────────────────────────────────────────┘
```

**关键设计:**

- **多轮工具调用:** 最多 MAX_TOOL_ROUNDS 轮（默认 10），防止死循环
- **对话记忆:** 完整保留 system/user/assistant/tool 消息链
- **错误处理:** 工具执行异常不会中断循环，错误信息回传给模型
- **全链路日志:** 每一步都写入 log.txt，可追溯 Agent 的完整思考过程

### 3.3 tools.py —— 工具定义

包含 7 个内置工具:

| 工具名 | 功能 |
| --- | --- |
| `run_shell_command` | 执行 shell 命令 (subprocess) |
| `read_file` | 读取文件内容 |
| `write_file` | 写入文件（自动创建父目录） |
| `list_directory` | 列出目录内容 |
| `search_files` | 按 glob 模式搜索文件 |
| `web_search` | 使用 Bing 搜索互联网 (urllib) |
| `web_fetch` | 获取指定 URL 的网页纯文本 (urllib) |

**扩展方法:**

1. 在 `TOOL_DEFINITIONS` 中添加 OpenAI 格式的函数描述
2. 实现对应的 Python 函数（签名: `func(**kwargs) -> str`）
3. 在 `TOOL_MAP` 中注册映射

### 3.4 logger.py —— 日志模块

负责将所有交互细节写入 log.txt，记录以下关键节点:

| 日志节点 | 内容 |
| --- | --- |
| SESSION START | 会话开始时间戳 |
| USER INPUT | 用户的原始输入文本 |
| LLM INPUT | 每轮发送给模型的完整 messages（摘要形式） |
| LLM RAW OUTPUT | 模型返回的 content + tool_calls 完整 JSON |
| TOOL EXECUTION | 工具名、参数 JSON、执行结果 |
| CONTEXT SNAPSHOT | 本轮结束后的对话历史全貌 |
| FINAL OUTPUT | 最终返回给用户的文本 |
| ERROR | 运行异常信息 |

**设计要点:**

- 追加写入，不覆盖历史 —— 每次运行都保留完整记录
- 超过 5MB 自动备份 —— 防止日志无限膨胀
- 超长内容自动截断 —— 工具结果 >500 字符、消息 >300 字符时截断
- 可通过 `LOG_ECHO=1` 同步输出到终端

### 3.5 config.py —— 配置管理

所有配置项均可通过环境变量覆盖:

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DEEPSEEK_API_KEY` | (无，必须设置) | DeepSeek API 密钥 |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | API 端点 |
| `DEEPSEEK_MODEL` | `deepseek-v4-flash` | 模型选择 |
| `AGENT_TEMPERATURE` | `0.0` | 生成温度 |
| `AGENT_MAX_TOKENS` | `4096` | 最大输出 token 数 |
| `AGENT_MAX_TOOL_ROUNDS` | `10` | 最大工具调用轮次 |
| `AGENT_LOG_PATH` | `log.txt` | 日志文件路径 |
| `AGENT_LOG_ECHO` | `0` | 设为 1 可同步终端输出 |
| `AGENT_WEB_TIMEOUT` | `30` | 网络请求超时秒数 |
| `AGENT_WEB_RETRIES` | `3` | 网络请求重试次数 |
| `AGENT_HTTP_PROXY` | (无) | HTTP(S) 代理地址 |
| `AGENT_HTTPS_PROXY` | (无) | 同上，优先级更高 |
| `AGENT_MCP_ENABLED` | `1` | 设为 0 可禁用 MCP |
| `AGENT_MCP_TOOL_PREFIX` | `mcp_` | MCP 工具名前缀 |
| `AGENT_MCP_CONNECT_TIMEOUT` | `10` | MCP 连接超时秒数 |

MCP 服务器配置在 `config.py` 的 `MCP_SERVERS` 列表中，每项格式:

```python
{
    "name":    "mcp_filesystem",        # 服务器名称（工具描述中标注）
    "command": "python",                # 启动命令
    "args":    ["D:\\...\\server.py"],  # 命令行参数
}
```

### 3.6 mcp_client.py —— MCP 客户端

MCP (Model Context Protocol) 是 Anthropic 提出的开放协议，用于 AI 模型与外部工具/数据源之间的标准化通信。本项目通过 stdio（标准输入输出）传输方式连接 MCP 服务器。

**架构:**

```
Agent (同步)
  │
  └→ MCPClientManager
       │  后台 asyncio 事件循环线程
       │
       ├→ MCPServerConnection (stdio 子进程)
       │    ├── connect()      → session.initialize()
       │    ├── list_tools()   → 发现远程工具
       │    ├── call_tool()    → 调用远程工具
       │    └── disconnect()   → 关闭会话
       │
       └→ tools.py
            ├── TOOL_DEFINITIONS ← MCP 工具(OpenAI 格式)
            └── TOOL_MAP        ← 闭包 → manager.call_tool()
```

**关键设计:**

- **工具名前缀:** MCP 工具名统一加 `mcp_` 前缀，避免与内置工具重名（如服务端 `read_file` → `mcp_read_file`）
- **异步桥接:** MCP 是 async 协议，Agent 是同步调用，通过后台事件循环线程 + `asyncio.run_coroutine_threadsafe()` 桥接
- **降级运行:** MCP 连接失败不阻断 Agent 启动，仅使用内置工具
- **即插即用:** 修改 `config.py` 的 `MCP_SERVERS` 列表即可添加更多服务器

**Agent 初始化流程:**

```
Agent.__init__()
  └→ _init_mcp()
       ├→ 检查 config.MCP_ENABLED
       ├→ MCPClientManager.connect_all()
       │    └→ 逐个连接 MCP_SERVERS 中的服务器
       │         ├→ 启动子进程 (python server.py)
       │         ├→ stdio_client() 建立双向管道
       │         ├→ session.initialize() 握手
       │         └→ session.list_tools() 发现工具
       └→ register_mcp_tools(manager)
            ├→ 清理旧的 MCP 工具（按前缀识别）
            ├→ TOOL_DEFINITIONS 追加 OpenAI 格式工具定义
            └→ TOOL_MAP 注册闭包（→ MCPClientManager.call_tool）
```

**工具调用流程:**

```
LLM 返回 tool_calls
  └→ TOOL_MAP["mcp_read_file"](**args)
       └→ MCPClientManager.call_tool("mcp_read_file", args)
            ├→ 查找 _tool_map 获取 (server_name, MCPTool)
            ├→ 获取对应的 MCPServerConnection
            └→ asyncio.run_coroutine_threadsafe(
                    conn.call_tool_async(tool.name, args)
                )
                 └→ session.call_tool(name, arguments)
                      └→ MCP 服务端处理 → 返回结果
```

**添加新 MCP 服务器:**

1. 在 `config.py` 的 `MCP_SERVERS` 列表中添加配置
2. 重启 Agent 即可自动发现并注册新工具

**示例 —— 连接到 MCP 文件系统服务器后:**

```
👤 You: 帮我在 MCP 目录下创建一个 test.txt
  [🔧 调用工具: mcp_write_file]
🤖 Agent: 已在 MCP 目录创建 test.txt。

👤 You: 列出 MCP 目录下所有文件
  [🔧 调用工具: mcp_list_directory]
🤖 Agent: MCP 目录下有 server.py, README.md, test.txt ...
```

### 3.7 web_ui.py + web/ —— Web 网页对话界面

前端使用 React 18 + Vite 构建，后端使用 Flask + SSE。支持流式输出、思考过程展示、可折叠工具调用卡、对话重置。

**架构:**

```
React (Vite :5173)            Flask 服务 (web_ui.py :5003)
         │                                      │
         ├─ GET  /health ────────────────────→ 模型信息
         │                                      │
         ├─ POST /chat {"message":"..."} ────→ Agent.run(user_input,
         │   (SSE 流)  ←── data: content ──      stream_callback)
         │             ←── data: reasoning ─      │
         │             ←── data: tool_call ─      │
         │             ←── data: tool_result      │
         │             ←── data: done ─────────   │
         │                                      │
         └─ POST /reset ─────────────────────→ Agent.reset()
```

**React 组件树:**

```
App (useReducer 状态管理)
├── Header          (模型标签 + 重置按钮)
├── ChatArea        (消息列表 + 智能滚动 + 空状态)
│   ├── MessageBubble  (用户/Agent 气泡)
│   │   └── 思考过程    (🧠 黄色内嵌区块，先于正文)
│   └── ToolCallCard   (🔧 可折叠工具卡，默认折叠)
└── InputArea       (输入框 + Enter 发送)
```

**SSE 事件类型:**

| 事件 | 说明 |
| --- | --- |
| `reasoning` | DeepSeek R1 思考过程（实时流式） |
| `content` | 模型输出的正文片段（实时流式） |
| `tool_call` | 工具调用开始（名称 + 参数） |
| `tool_result` | 工具执行结果 |
| `done` | 本轮对话完成 |
| `error` | 错误信息 |

**技术要点:**

- 前端: React 18 + useReducer 管理消息状态，不可变更新
- 后端: Agent 运行在后台线程，通过 `queue.Queue` 传递事件给 SSE
- 智能滚动: 仅当用户在底部 80px 以内时才自动跟随，不抢焦点
- 共享实例: 整个服务共享一个 Agent 单例，reset 用于切换会话

## 四、快速开始

### 4.1 安装依赖

```bash
# Python 依赖
pip install -r requirements.txt

# 前端依赖（仅 Web UI 需要）
cd web && npm install
```

### 4.2 设置 API Key

**Windows:**
```bash
set DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxx
```

**Linux / Mac:**
```bash
export DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxx
```

API Key 获取地址: https://platform.deepseek.com/api_keys

### 4.3 运行

```bash
# 交互模式
python main.py

# 单次模式
python main.py "列出当前目录的所有文件"

# 使用 Pro 模型（更强大的推理能力）
set DEEPSEEK_MODEL=deepseek-v4-pro
python main.py

# 同步输出日志到终端（调试时有用）
set AGENT_LOG_ECHO=1
python main.py
```

### 4.4 Web UI 模式（网页对话）

Web UI 提供两种运行模式：

**── 生产模式（推荐日常使用）──**

1. 构建 React 前端（首次或代码更新后执行一次）:
   ```bash
   cd web
   npm install    # 首次需安装依赖
   npm run build  # 构建到 web/dist/
   ```

2. 启动 Flask 服务:
   ```bash
   python web_ui.py
   ```

3. 浏览器访问 `http://localhost:5003`
   Flask 会自动检测 `web/dist/` 存在，serve React 前端。

**── 开发模式（修改前端代码时使用）──**

1. 安装前端依赖（首次）:
   ```bash
   cd web && npm install
   ```

2. 终端 A —— 启动 Flask 后端:
   ```bash
   python web_ui.py   # 端口 5003
   ```

3. 终端 B —— 启动 Vite 开发服务器:
   ```bash
   cd web && npm run dev   # 端口 5173，代理 API → :5003
   ```

4. 浏览器访问 `http://localhost:5173`
   Vite 支持 HMR 热更新，修改前端代码即时生效。

**── 自定义端口 ──**

```bash
set FLASK_PORT=8080
python web_ui.py
```

### 4.5 示例对话

```
👤 You: 在当前目录创建一个 hello.py，内容是打印 Hello World
  [🔧 调用工具: write_file]
🤖 Agent: 已在当前目录创建 hello.py，内容为 print("Hello World")。

👤 You: 运行一下这个文件
  [🔧 调用工具: run_shell_command]
🤖 Agent: 执行结果输出 "Hello World"，文件运行正常。

👤 You: 搜索所有 .py 文件
  [🔧 调用工具: search_files]
🤖 Agent: 当前目录下找到以下 .py 文件:
  - hello.py
  - main.py
  - agent.py
  ...

👤 You: 帮我查一下 Python 3.12 有什么新特性
  [🔧 调用工具: web_search]
🤖 Agent: 根据搜索结果，Python 3.12 的主要新特性包括:
  1. 更灵活的 f-string 解析 (PEP 701)
  2. 类型形参语法 (PEP 695)
  3. 改进的错误消息
  ...

👤 You: 把第一个搜索结果的详细内容拉下来看看
  [🔧 调用工具: web_fetch]
🤖 Agent: 以下是该页面的详细内容摘要: ...
```

### 4.6 log.txt 输出示例

以上对话在 log.txt 中的记录节选:

```
================================================================================
  SESSION START — 2025-06-03 14:30:00
================================================================================

┌─ USER INPUT ------------------------------------------------------------------
│ 列出当前目录的所有文件
└-------------------------------------------------------------------------------

┌─ [ROUND 1] LLM INPUT —— 发送给模型的 messages (2 条) --------------------------
│ msg[0] [system] 你是一个实用的 AI 助手，可以调用工具来完成用户的任务...
│ msg[1] [user] 列出当前目录的所有文件
├─ INPUT END (共 2 messages)---------------------------------------------------

┌─ [ROUND 1] LLM RAW OUTPUT —— 模型原始返回 ------------------------------------
│ content: None
│ tool_calls (1 个):
│ {
│   "id": "call_xxxxxxxxxxxx",
│   "type": "function",
│   "function": {
│     "name": "list_directory",
│     "arguments": "{\"dirpath\": \".\"}"
│   }
│ }
└-------------------------------------------------------------------------------

┌─ [ROUND 1] TOOL EXECUTION ----------------------------------------------------
│ 工具名: list_directory
│ 参数:   {"dirpath": "."}
│ 结果:
│   目录 D:\DATA\PythonProj\agent_test 的内容:
│     agent.py
│     config.py
│     logger.py
│     main.py
│     README.txt
│     requirements.txt
│     tools.py
└-------------------------------------------------------------------------------

┌─ [ROUND 1] CONTEXT SNAPSHOT —— 当前对话历史 (4 条) ---------------------------
│ [0] [system] 你是一个实用的 AI 助手...
│ [1] [user] 列出当前目录的所有文件
│ [2] [assistant] (no content) + tool_calls: ['list_directory']
│ [3] [tool] tool_call_id=call_xxxxxxxxxxxx
│ 目录 D:\DATA\PythonProj\agent_test 的内容: ...
└-------------------------------------------------------------------------------

┌─ [ROUND 2] LLM INPUT —— 发送给模型的 messages (4 条) -------------------------
│ ... (继续下一轮调用，模型基于工具结果生成最终回复)
└-------------------------------------------------------------------------------

┌─ FINAL OUTPUT ----------------------------------------------------------------
│ 当前目录下共有 6 个文件：agent.py、config.py、logger.py、main.py、
│ README.txt、requirements.txt 和 tools.py。
└-------------------------------------------------------------------------------
```

## 五、API 参考 —— `OpenAI.chat.completions.create()` 完整参数手册

本项目核心调用为 OpenAI Python SDK 的 `client.chat.completions.create()`。以下逐一解释每一个输入参数和返回对象，基于 `openai>=1.0.0`。

### 第一部分：输入参数（按字母序排列）

#### 5.1.1 `messages` (list[dict], 必填)

对话历史列表，按时间顺序排列。每条消息是一个 dict，必须包含 `role` 和 `content`（或 `tool_calls` / `tool_call_id`）。

**支持的 role 类型:**

| role | 说明 |
| --- | --- |
| `system` | 系统级指令，设定 AI 的行为、角色、输出格式。放在 `messages[0]`。模型对此角色最敏感，用于注入不可违背的规则。示例: `{"role":"system","content":"你是一个 Python 专家"}` |
| `user` | 用户输入。可以是纯文本或多模态（图片 URL / base64）。示例: `{"role":"user","content":"帮我写一个快速排序"}` |
| `assistant` | 模型的历史回复。有两种形态: (a) 纯文本 `{"role":"assistant","content":"好的，代码如下..."}` (b) 工具调用 `{"role":"assistant","content":null,"tool_calls":[...]}`。注意: content 在工具调用时可为 null 或附带简短的思考文本。 |
| `tool` | 工具执行结果，必须配合 `tool_call_id` 指明是为哪个 tool_call 的返回值。content 是工具输出的字符串（可以是 JSON 字符串）。示例: `{"role":"tool","tool_call_id":"call_xx","content":"文件内容: print('hello')\n"}` |

本项目 `agent.py` 中的用法: `self.messages` 列表依次追加 `user → assistant(tool_calls) → tool → assistant(text)`，形成完整对话链。

#### 5.1.2 `model` (str, 必填)

指定要调用的模型 ID。

**DeepSeek 可用模型:**

| 模型 | 说明 |
| --- | --- |
| `deepseek-v4-pro` | 旗舰模型，推理最强，适合复杂 Agent 任务 |
| `deepseek-v4-flash` | 轻量模型，速度快/成本低，适合简单对话 |

本项目默认: `config.MODEL = "deepseek-v4-flash"`

#### 5.1.3 `tools` (list[dict], 可选)

定义模型可调用的外部工具（即 function calling）。每个工具是一个 dict，包含 `type` 和 `function` 两个顶层字段:

```json
{
  "type": "function",
  "function": {
    "name": "get_weather",
    "description": "获取天气",
    "parameters": {
      "type": "object",
      "properties": {
        "location": {
          "type": "string",
          "description": "城市名"
        }
      },
      "required": ["location"]
    }
  }
}
```

本项目 `tools.py` 中 `TOOL_DEFINITIONS` 即为此参数的值。工具数量限制: DeepSeek 建议 ≤ 128 个。

#### 5.1.4 `tool_choice` (str \| dict, 可选)

控制模型是否以及如何调用工具。

| 值 | 说明 |
| --- | --- |
| `"auto"` (默认) | 模型自行决定是回复文本还是调用工具 |
| `"none"` | 强制模型不调用任何工具（即使传了 tools） |
| `"required"` | 强制模型必须调用至少一个工具 |
| `{"type":"function","function":{"name":"my_func"}}` | 强制调用特定函数 |

本项目未显式设置（使用默认 auto），模型会自主判断。

#### 5.1.5 `temperature` (float, 可选, 默认 1.0, 范围 0~2)

采样温度。越高则输出越随机（更有创意），越低则越确定（更保守）。设为 0 并非绝对确定，但极大减少随机性。

建议: Agent/工具调用场景用 0.0~0.3，创意写作场景用 0.7~1.0。本项目默认: `config.TEMPERATURE = 0.0`

#### 5.1.6 `top_p` (float, 可选, 默认 1.0, 范围 0~1)

核采样 (nucleus sampling)。模型仅从累积概率 ≥ top_p 的 token 中采样。通常与 temperature 二选一，不建议同时修改两者。本项目未使用（保持默认 1.0）。

#### 5.1.7 `max_tokens` / `max_completion_tokens` (int, 可选)

限制模型输出的最大 token 数（含文本 + 工具调用）。注意: 不会截断单条消息，而是在达到上限时终止生成。

- OpenAI: `max_completion_tokens` (推荐，v1.82+ 替代 max_tokens)
- DeepSeek: `max_tokens`（也支持 max_completion_tokens）

本项目默认: `config.MAX_TOKENS = 4096`

#### 5.1.8 `stream` (bool, 可选, 默认 False)

是否启用流式输出 (SSE)。开启后 API 逐 token 返回，实现打字机效果。

- `True`: 返回一个迭代器，需遍历 chunks 收集完整内容
- `False`: 一次性返回完整响应

本项目默认: `stream=False`（一次性获取完整响应以便日志记录）

#### 5.1.9 `stream_options` (dict, 可选)

仅在 `stream=True` 时有效。控制流式响应的附加信息: `{"include_usage": True}` 在流的最后 chunk 中包含 usage 统计。本项目未使用。

#### 5.1.10 `stop` (str \| list[str], 可选)

停止序列。模型生成到这些字符串中的任意一个时立即停止。最多 4 个序列。示例: `stop=["\n\n", "END"]`。本项目未使用。

#### 5.1.11 `presence_penalty` (float, 可选, 默认 0, 范围 -2~2)

正数惩罚已出现过的 token，鼓励模型谈论新话题。负数则反之，允许重复。本项目未使用。

#### 5.1.12 `frequency_penalty` (float, 可选, 默认 0, 范围 -2~2)

正数按 token 在文本中出现的频率比例惩罚，减少逐字重复。与 presence_penalty 的区别: 这是频率惩罚，presence 是存在性惩罚。本项目未使用。

#### 5.1.13 `logit_bias` (dict[str, int], 可选)

修改指定 token 在采样前的 logit 值。key 为 token ID (字符串)，value 为偏置值 (-100 到 100)。可用来强制或禁止某些词的出现。示例: `{"12345": -100}` 彻底禁止 token 12345。本项目未使用。

#### 5.1.14 `n` (int, 可选, 默认 1)

为每条输入生成多少个候选回复。n > 1 时会返回多个 choices。注意: 会消耗 n 倍 token 预算。本项目默认: n=1（未显式设置）。

#### 5.1.15 `seed` (int, 可选)

尽量使输出确定化的随机种子。配合 `system_fingerprint` 可复现结果。但不等同于完全确定性，硬件浮点计算仍有微小差异。本项目未使用。

#### 5.1.16 `response_format` (dict, 可选)

强制模型按指定格式输出。

| 值 | 说明 |
| --- | --- |
| `{"type": "text"}` | (默认) 普通文本 |
| `{"type": "json_object"}` | 强制输出合法 JSON |
| `{"type": "json_schema", "json_schema": {...}}` | 按 JSON Schema 严格输出结构化数据 |

注意: `json_object` 模式需要在 prompt 中显式提到 "JSON"。`json_schema` 模式支持 strict 类型校验（仅部分 OpenAI 模型）。本项目未使用。

#### 5.1.17 `parallel_tool_calls` (bool, 可选, 默认 True)

是否允许模型在一次回复中并行调用多个工具。

- `True`: 模型可一次返回多个 tool_calls（如同时读两个文件）
- `False`: 模型每次只能调用一个工具

本项目默认: True（未显式设置），`agent.py` 的循环支持逐个处理多个 tool_calls。

#### 5.1.18 `user` (str, 可选)

终端用户标识符，用于 OpenAI 的滥用监控。本项目未使用。

#### 5.1.19 `reasoning_effort` (str, 可选)

仅推理模型（如 o1 / o3）支持。控制推理深度: `"low"` / `"medium"` / `"high"`。DeepSeek 不直接支持此参数，通过 `extra_body` 启用 thinking 模式。本项目未使用。

#### 5.1.20 `extra_body` (dict, 可选)

OpenAI SDK 提供的扩展入口，将自定义字段注入请求体。

DeepSeek 专用: 启用思考链 (thinking mode):
```python
extra_body={"thinking": {"type": "enabled"}}
```

启用后模型会返回 `reasoning_content`（思考过程文本），不额外计费。本项目未默认启用，可在 `agent.py` 的 `create()` 调用中添加。

### 第二部分：返回值 (ChatCompletionResponse)

`create()` 返回一个 `ChatCompletion` 对象（下面用 `response` 指代），其顶层字段如下:

#### 5.2.1 `response.id` (str)

本次 API 调用的唯一标识符，形如 `"chatcmpl-xxxxxxxx"`。用于问题排查、日志追踪、向 OpenAI/DeepSeek 报告问题时引用。

#### 5.2.2 `response.object` (str)

固定值 `"chat.completion"`，表示这是一个聊天完成响应。

#### 5.2.3 `response.created` (int)

Unix 时间戳（秒），表示响应生成时刻。

#### 5.2.4 `response.model` (str)

实际处理本次请求的模型名。可能与请求中指定的不同（如 API 内部路由到不同版本）。

#### 5.2.5 `response.choices` (list[Choice])

模型生成的候选回复列表，通常只取 `choices[0]`。每个 Choice 包含:

| 字段 | 说明 |
| --- | --- |
| `choices[i].index` (int) | 该候选的序号（0 起） |
| `choices[i].message` | **核心字段** —— 模型生成的消息对象 |
| `choices[i].finish_reason` (str) | 生成结束的原因 |
| `choices[i].logprobs` | 每个输出 token 的对数概率（需请求时指定 logprobs=True） |

**`message` (ChatCompletionMessage) 子字段:**

| 字段 | 说明 |
| --- | --- |
| `message.role` (str) | 固定为 `"assistant"` |
| `message.content` (str \| None) | 模型的文本回复。当模型调用工具时为 None |
| `message.tool_calls` (list[ToolCall] \| None) | **工具调用核心** —— 当模型决定调用工具时非空 |
| `message.reasoning_content` (str \| None) | 思考过程文本。仅当启用了 thinking/推理模式时返回 |

**ToolCall 子字段:**

| 字段 | 说明 |
| --- | --- |
| `tool_call.id` (str) | 本次工具调用的唯一 ID，形如 `"call_xxxxxxxxxxxx"` |
| `tool_call.type` (str) | 固定为 `"function"` |
| `tool_call.function.name` (str) | 模型决定调用的函数名 |
| `tool_call.function.arguments` (str) | JSON 字符串，包含函数调用的实参。需用 `json.loads()` 解析 |

**`finish_reason` 取值:**

| 值 | 说明 |
| --- | --- |
| `"stop"` | 自然结束或命中 stop 序列 |
| `"length"` | 达到 max_tokens 限制 |
| `"tool_calls"` | 模型请求调用工具（非文本结束） |
| `"content_filter"` | 内容被安全过滤器拦截 |
| `"function_call"` | (已废弃，等同于 tool_calls) |

#### 5.2.6 `response.usage` (CompletionUsage \| None)

Token 使用统计，`stream=False` 时必返回:

| 字段 | 说明 |
| --- | --- |
| `usage.prompt_tokens` (int) | 输入消息消耗的 token 数（含 system/user/assistant/tool 及工具定义） |
| `usage.completion_tokens` (int) | 模型输出消耗的 token 数（含 content 和 tool_calls） |
| `usage.total_tokens` (int) | prompt_tokens + completion_tokens |

注意: `stream=True` 时默认不返回 usage。需设 `stream_options` 来获取。

#### 5.2.7 `response.system_fingerprint` (str \| None)

后端配置的指纹。当此值变化时说明模型后端的运行环境发生了变更（可能影响输出）。结合 seed 参数可判断输出是否可复现。

#### 5.2.8 `response.service_tier` (str \| None)

OpenAI 特定: 服务层级，如 `"default"` 或 `"flex"`。DeepSeek 不返回此字段。

### 第三部分：本项目中的实际调用链路

#### 5.3.1 Agent 的 create() 调用

```python
# agent.py 第 89-95 行
response = self.client.chat.completions.create(
    model=self.model,           # 从 config.MODEL 读取
    messages=self.messages,     # 完整对话历史
    tools=TOOL_DEFINITIONS,     # 工具定义
    temperature=config.TEMPERATURE,  # 默认 0.0
    max_tokens=config.MAX_TOKENS,    # 默认 4096
)

# 解析返回值
choice = response.choices[0]         # 取第一个候选
msg = choice.message                 # ChatCompletionMessage 对象

# 判断分支
if msg.tool_calls:                   # 模型要调用工具
    执行工具 → 结果回传 → 再次 create()
else:                                # 模型返回最终文本
    final_text = msg.content         # 展示给用户
    return final_text
```

#### 5.3.2 工具调用协议的完整流程

一次完整的工具调用涉及两次 `create()`:

```
第一次 create():
  INPUT:  [system, user]
  OUTPUT: msg.content=None, msg.tool_calls=[{name:"list_directory"}]
  → Agent 执行 list_directory(dirpath=".") → 得到结果字符串
  → messages 追加 assistant(tool_calls) 和 tool(result)

第二次 create():
  INPUT:  [system, user, assistant(tool_calls), tool(result)]
  OUTPUT: msg.content="当前目录包含以下文件: ..." , tool_calls=None
  → finish_reason="stop" → 最终返回给用户
```

#### 5.3.3 log.txt 记录的对应关系

log.txt 中每轮 LLM INPUT 对应一次 `create()` 的 messages 参数。LLM RAW OUTPUT 对应 `response.choices[0].message` 的完整内容。TOOL EXECUTION 对应用户侧执行的结果。

完整链路: `USER INPUT → LLM INPUT(messages) → LLM RAW OUTPUT(content+tool_calls JSON) → TOOL EXECUTION(参数+结果) → CONTEXT SNAPSHOT → 下一轮 LLM INPUT → ... → FINAL OUTPUT`

#### 5.3.4 安全注意事项

- `run_shell_command` 使用 `shell=True`，请勿在不可信环境运行
- 建议仅用于本地开发，生产环境应进行沙箱隔离
- 工具执行有超时机制，防止命令挂死
- API Key 仅通过环境变量传入，不会写入日志文件
- 日志文件可能包含敏感信息（命令输出等），请妥善保管

### 5.4 深入原理：大模型如何使用 tools JSON 决定调用工具

这是一个常被误解的核心问题。`tools` 参数传入的不是"可执行代码"，模型也不会真的"运行"这些函数。整个机制分为三个层面：训练层面、推理层面、工程层面。

#### 5.4.1 训练层面：模型如何学会"看懂"tools JSON

大模型在预训练阶段从未见过 tools JSON 格式。这种能力来自 fine-tuning（微调）阶段的专门训练：

1. **构造训练数据:** OpenAI / DeepSeek 用大量 "用户请求 + 可用工具定义 + 正确的 tool_calls 输出" 三元组来微调模型。
2. **强化学习对齐 (RLHF / DPO):** 进一步训练模型在"应该调用工具时调用工具"、"不该调用时老老实实回复文本"。惩罚两类错误：该调不调（漏报）和不该调乱调（误报）。
3. **学到的能力:** 经过上述训练，模型内化了: (a) 解析 JSON Schema (b) 语义匹配 (c) 参数填充 (d) 格式遵循

> **关键洞察:** 模型的这些能力是通过海量示例"背诵"出来的，而非真的理解了 JSON Schema 规范。这也解释了为什么它偶尔会生成不存在的参数名或错误类型 —— 本质是模式匹配，不是形式化推理。

#### 5.4.2 推理层面：一次 tool call 决策在模型内部的完整过程

当 `client.chat.completions.create()` 被调用时:

```
Step 1: 输入序列化
  SDK 将所有输入拼接为一个 token 序列:
  [system prompt tokens] [user message tokens] [tools JSON tokens]
  tools 定义被直接当作上下文注入！

Step 2: Transformer 前向传播
  整个 token 序列通过多层 Transformer:
  • 注意力机制让每个 token 都能"看到"所有其他 token
    → user 的 "天气" 可以 attend 到 tools 中的 "name":"get_weather"
  • 前馈网络层做语义计算:
    "用户问了天气 + 有工具能获取天气 + 用户提到了地点 = 应该调用 get_weather("北京")"

Step 3: 输出生成（自回归解码）
  模型逐 token 生成输出。当它"决定"调用工具时，会生成特殊结构

Step 4: API 服务器后处理
  API 服务器（DeepSeek 后端）对模型原始输出做:
  a) 解析特殊标记，提取 tool_calls JSON
  b) 验证 JSON 格式合法性
  c) 填充 message.content = None（工具调用时）
  d) 填充 finish_reason = "tool_calls"
  e) 组装成标准 ChatCompletion 响应返回
```

#### 5.4.3 参数提取机制：模型如何从对话中"填入"arguments

这是最精妙的部分。模型不是通过代码逻辑 "if 用户说了城市 then 填入 location"，而是通过注意力机制做软性的信息聚合。

以 `tools.py` 中的 `list_directory` 为例:

- 用户输入 "看看当前目录下有什么文件" → 模型通过 attention 将 "当前目录" 与 `dirpath.description = "默认 '.'"` 关联 → 生成 `arguments: '{"dirpath": "."}'`
- 用户输入 "看看 /tmp 目录" → "tmp" 高注意力到 dirpath → 生成 `arguments: '{"dirpath": "/tmp"}'`

对比用户输入 "创建一个 hello.py 输出 Hello World":

```
模型内部并行评估工具:
  run_shell_command:  语义匹配度低
  read_file:          语义匹配度低
  write_file:         语义匹配度高 ✓ "创建"+"内容"
  list_directory:     语义匹配度低
  search_files:       语义匹配度低
  → 选择 write_file

参数填充:
  "hello.py" → attention 到 filepath.description
  "输出 Hello World" → attention 到 content.description
  → arguments: '{"filepath":"hello.py","content":"print(\"Hello World\")"}'
```

> 注意: "语义匹配度" 不是模型显式输出的数值，而是对注意力分布和最终 logit 的一个概念性描述。选择是注意力机制 + 前馈网络 + 自回归解码联合完成的涌现行为。

#### 5.4.4 JSON Schema 各字段对模型行为的具体影响

| 字段 | 影响 |
| --- | --- |
| `name` (函数名) | 模型通过函数名的语义来判断工具的功能类别。命名不当会导致模型选错工具。 |
| `description` (描述) | **这是模型判断是否调用工具的最重要依据。** 好的 description 应说清楚: 做什么、什么时候用、有什么限制。 |
| `parameters.properties` | 每个参数的 name 和 description 决定了模型如何从对话中提取值。description 越精确，填充越准确。 |
| `parameters.required` | 告诉模型哪些参数不能省略。理想情况下模型会尽量确保必填参数都被填充。 |
| `parameters.type` | 模型经过训练能遵循类型约束。string 参数会被填充字符串，integer 会被填充数字。 |
| `enum` | 限制参数的合法取值。模型会尽量选择 enum 中的值。 |

#### 5.4.5 工程层面：SDK 和 API 服务器在各环节的角色

```
┌──────────┐    ┌──────────────┐    ┌──────────────┐
│ 客户端    │    │ API 服务器    │    │ 模型推理引擎  │
│ (agent.py)│    │ (DeepSeek)   │    │ (GPU 集群)   │
└─────┬─────┘    └──────┬───────┘    └──────┬───────┘
      │                 │                   │
      │ ① 构造 tools    │                   │
      │   JSON 定义     │                   │
      │ ② 发送 HTTPS    │                   │
      │   POST ────────→│                   │
      │                 │ ③ 鉴权/限流       │
      │                 │ ④ 序列化为 tokens  │
      │                 │   ────────────────→│
      │                 │                   │ ⑤ Transformer 前向传播
      │                 │                   │   注意力跨 user/tools
      │                 │                   │   逐 token 自回归生成
      │                 │ ⑥ 解析特殊标记    │
      │                 │   验证 JSON 合法性 │
      │                 │   组装响应体       │
      │ ⑦ 解析 JSON     │                   │
      │   response ←────│                   │
      │ ⑧ 提取 tool_calls│                  │
      │   本地执行函数   │                   │
      │   结果追加回     │                   │
      │   messages       │                   │
      │ ⑨ 再次 ②→...    │                   │
      │   直到模型返回   │                   │
      │   纯文本回复     │                   │
```

**核心结论:**

1. tools JSON 是"上下文"而非"代码" —— 以 token 形式注入模型
2. 模型通过训练获得的模式匹配能力来"理解" tools
3. 模型输出 tool_calls 字符串，真正的函数执行在客户端
4. 工具结果以 `role="tool"` 消息形式回传，模型据此继续推理

#### 5.4.6 常见误区澄清

| 误区 | 事实 |
| --- | --- |
| "模型会执行 tools 中定义的函数" | 模型只输出函数名和参数 JSON 字符串。真正的执行是你的 Python 代码（agent.py 中的 `_execute_tool` / `TOOL_MAP`）。 |
| "tools 定义得越详细模型就越准确" | 描述的质量 > 描述的数量。过长的 tools 会挤占 messages 的 token 预算。 |
| "模型看到 function name 就知道怎么用了" | description 比 name 更重要。模型主要靠 description 做语义匹配。 |
| "模型能精确遵循 JSON Schema 的类型约束" | 在没有 strict 模式时，模型对 JSON Schema 的遵循是"尽力而为"的统计行为，不是确定性保证。 |
| "tool_calls 里的 arguments 已经是 Python dict" | `arguments` 是一个 JSON 字符串，必须用 `json.loads()` 解析。 |

#### 5.4.7 协议细节：tools 的序列化、与 messages 的关系

**问题①: tools 的序列化过程**

在 HTTP 请求体中，`tools` 是 `messages` 的兄弟字段，而非子字段:

```json
{
  "model": "deepseek-v4-flash",
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user",   "content": "..."}
  ],
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "get_weather",
        "description": "...",
        "parameters": { ... }
      }
    }
  ],
  "temperature": 0.0,
  "max_tokens": 4096
}
```

tools 到达 API 服务器后，被转换为模型可消费的 token 序列，拼接到 messages 的 token 序列中，形成模型最终"看到"的一维数组: `[system tokens] [user tokens] [tools tokens]`。

验证: tools 定义会消耗 prompt_tokens。本项目的几个工具约消耗 800~1200 tokens。

**问题②: 为什么 messages 里没有 tools？**

- **语义混乱:** messages 里每条的 role 代表对话参与者。tools 不是任何人"说的话"，它是元数据。
- **客户端状态管理复杂化:** 如果 tools 也在 messages 里，每次 create() 都需要小心处理追加 vs 保留。
- **服务端优化空间:** API 服务器可以对 tools 做特殊处理（KV-cache 复用、格式转换、校验）。

**问题③: 把 tools 写在 system message 里 vs 用 tools 参数**

| | 写在 system message | tools 参数 |
| --- | --- | --- |
| 格式 | 自然语言 / 自由格式 | JSON Schema |
| 训练匹配度 | 低。模型没见过此格式 | 高。专门微调过 |
| 输出格式 | 模型输出自然语言文本，需自行正则/解析提取 | 模型输出结构化 tool_calls JSON，可直接反序列化 |
| 参数约束 | 无。模型可能编造参数名 | 有。JSON Schema 约束 + required |
| 类型安全 | 无 | type:integer 可减少类型错误 |
| 并行调用 | 很难 | 原生支持 |
| 服务端校验 | 无 | strict 模式下服务端校验 Schema |
| 预期行为 | 不可靠 | 可靠 |
| token 消耗 | 取决于描述篇幅（通常更省） | 取决于工具数量（Schema 冗长） |

**结论:** 写在 system message 里是"用自然语言请求模型帮你调用"，用 tools 参数是"用结构化协议让模型输出可编程的调用指令"。前者是 hack，后者是正式 API。任何严肃的 Agent 项目都应使用 tools。

#### 5.4.8 实践评估：手写 tools 文本 + 正则解析 vs 原生 tools 参数

**简短回答:** 对 DeepSeek/OpenAI 等已原生支持 tool calling 的模型，不推荐手写方案。但对特定场景（旧模型、极致 token 优化、自定义格式需求）这是合理的技术选型。

**优势:**

1. token 消耗更低（200~400 vs 800~1200 tokens）
2. 兼容任意模型（包括不支持原生 tool calling 的开源模型）
3. 格式完全可控（可加入自定义字段如 `<reasoning>`、`<confidence>`）
4. 可在工具定义中混入动态指令

**劣势:**

1. **解析脆弱性** —— 这是最致命的问题。模型可能输出各种变体格式，正则难以全覆盖。
2. 没有类型约束
3. 无法利用 parallel_tool_calls
4. finish_reason 不可靠（始终为 "stop"）
5. 模型可能遗忘格式（"迷失在中间"问题）
6. 没有服务端兜底

**决策矩阵:**

| 你的场景 | 推荐方案 |
| --- | --- |
| DeepSeek/OpenAI + Agent 开发 | 原生 tools 参数 |
| 本地开源模型不支持 tool calling | 手写 prompt + 正则 |
| 极致 token 优化（嵌入式/批量调用） | 手写 prompt + 正则 |
| 生产环境 / 需要可靠性 | 原生 tools 参数 |
| 工具数量 > 10 | 原生 tools 参数 |
| 需要并行调用 | 原生 tools 参数 |

**本项目为什么选择原生 tools:**

1. DeepSeek 的 tool calling 微调质量高
2. agent.py 的循环依赖 finish_reason 来判断是否继续
3. 工具 JSON Schema 约占 1000 tokens，在 128K 上下文中占比不到 1%
4. logger.py 需要解析原始 tool_calls 来展示调用链

#### 5.4.9 底层机制：模型逐 token 输出，function 字段从何而来？

**你拿到的 response 不是模型的原始输出。** 它是 API 服务器对原始 token 流做了"解析-剥离-重组"之后的产物。

```
模型输出:  一维 token 流（含特殊控制 token）
      ↓
API 服务器: 拦截特殊 token → 剥离 → 解析 JSON → 结构化为
            message.content / message.tool_calls / finish_reason
      ↓
你拿到:    干干净净的 Python 对象（Choice.message）
```

模型输出的是带特殊标记（`<|start_tool_call|>` / `<|end_tool_call|>`）的 token 序列。API 服务器的后处理层检测到这些特殊 token 后，将内容解析为 tool_calls JSON，content 置为 None（因为所有 token 都被识别为工具调用的一部分）。

> **核心结论:** function 字段不是模型"输出了一个对象"，而是模型输出了带特殊标记的 token 序列，API 服务器的后处理层把这些 token 翻译成了你看到的 tool_calls 结构。

### 5.5 Agent 循环的终止条件：不只是 "无 tool_calls"

直觉上，Agent 循环的终止条件是"模型不再调用工具"。但实际远比这复杂。因为 `finish_reason` 才是判断模型状态的真正依据，`tool_calls` 只是表象。

#### 5.5.1 三种终止路径

| 路径 | 条件 | 行为 |
| --- | --- | --- |
| **A —— 自然终止** | finish_reason="stop" + 无 tool_calls | 返回 msg.content 给用户。日志: FINAL OUTPUT |
| **B —— 工具调用循环** | finish_reason="tool_calls" | 执行工具 → 结果回传 → 下一轮 create()。日志: TOOL EXECUTION → CONTEXT SNAPSHOT |
| **C —— 强制终止** | 达到 MAX_TOOL_ROUNDS | 返回兜底文本。日志: LIMIT REACHED |

#### 5.5.2 三个容易被误判为"最终回复"的 finish_reason

| finish_reason | tool_calls | 旧逻辑 | 实际含义 |
| --- | --- | --- | --- |
| `"stop"` | None | ✅ 正确终止 | 自然结束 |
| `"tool_calls"` | 有数据 | ✅ 继续循环 | 请求调用工具 |
| `"length"` | None | ❌ 误当最终回复 | 输出被截断！ |
| `"content_filter"` | None | ❌ 误当最终回复 | 内容被过滤！ |
| None | None | ❌ 行为未定义 | 异常状态 |

- **案例 1: finish_reason="length"** —— MAX_TOKENS=500，模型要输出 800 tokens 的代码时被截断。旧逻辑当作最终回复返回 → 用户拿到半截代码。新逻辑: 检测到 length → 追加系统消息 "请继续完成你的回复" → 再给模型一轮。
- **案例 2: finish_reason="content_filter"** —— 内容被安全策略拦截。旧逻辑返回空字符串。新逻辑: 返回明确提示 "回复被内容安全过滤器拦截"。

#### 5.5.3 完整终止判断流程图

```
新一轮 create() 返回
      │
      ▼
┌─────────────┐
│ msg.tool_   │── 有 ──→ 执行工具 → 结果回传 → 回到循环开头
│ calls?      │
└──────┬──────┘
       │ 无
       ▼
┌──────────────────────────────────────────────┐
│ choice.finish_reason?                         │
├──────────────────────────────────────────────┤
│ "stop"           → ✅ 自然终止，返回 content │
│ "length"         → ⚠ 截断，追加 continue    │
│                     提示后回到循环开头       │
│ "content_filter" → 🚫 安全拦截，返回提示     │
│ "tool_calls"     → (不应出现，tool_calls     │
│                     已在上方处理)            │
│ None / 其他      → ❓ 保守处理，按文本返回   │
└──────────────────────────────────────────────┘

附加终止条件: 超过 MAX_TOOL_ROUNDS → 强制退出
```

#### 5.5.4 工具调用死循环的防护

本项目的防护措施:

1. **MAX_TOOL_ROUNDS 硬上限**（默认 10）—— 最可靠的防护
2. **工具错误信息回传** —— 工具执行失败时返回明确的错误字符串
3. **finish_reason="length" 自动续写** —— 防止因 max_tokens 不够导致的"假终止"
4. **每个工具的 description 中写明适用场景和限制** —— 帮助模型做出更准确的判断

未来可增强的防护: 重复调用检测、空结果检测、token 预算监控。

#### 5.5.5 stream=True 时的终止判断差异

本项目使用 `stream=False`，一次性获取完整响应，终止判断在拿到完整 response 后一次完成。

如果使用 `stream=True`，情况更复杂: tool_calls 和 finish_reason 分布在不同的 chunk 中，必须累积所有 chunk 才能做终止判断。这也是本项目选择 `stream=False` 的原因之一: 终止条件判断简单可靠。

## 六、二次开发指南

### 6.1 添加自定义工具

在 `tools.py` 中:

```python
# Step 1: 实现函数
def _my_tool(param1: str) -> str:
    return f"处理结果: {param1}"

# Step 2: 添加 OpenAI 格式定义
{
    "type": "function",
    "function": {
        "name": "my_tool",
        "description": "工具描述",
        "parameters": {
            "type": "object",
            "properties": {
                "param1": {"type": "string", "description": "参数说明"}
            },
            "required": ["param1"]
        }
    }
}

# Step 3: 注册
TOOL_MAP["my_tool"] = _my_tool
```

### 6.2 自定义系统提示词

```python
agent = Agent(system_prompt="你是一个专业的 Python 开发助手...")
```

### 6.3 切换模型

推荐:

| 模型 | 适用场景 |
| --- | --- |
| `deepseek-v4-flash` | 日常任务，速度快、成本低 |
| `deepseek-v4-pro` | 复杂推理，效果最优 |

```python
agent = Agent(model="deepseek-v4-pro")
```

### 6.4 在代码中（非命令行）使用 Agent

```python
from agent import Agent

agent = Agent()
result = agent.run("列出当前目录的文件")
print(result)
# log.txt 中已有完整记录

agent.reset()  # 重置对话，开始新任务
```

## 七、常见问题

**Q: 提示 "❌ 错误: 请先设置环境变量 DEEPSEEK_API_KEY"**

A: 需要先获取 API Key（https://platform.deepseek.com/api_keys），然后按第四节设置环境变量。

**Q: 工具调用一直循环不停**

A: 检查 `config.MAX_TOOL_ROUNDS` 是否过大（默认 10）。工具返回的错误信息是否足够清晰让模型判断已失败。可通过 `log.txt` 查看每一轮模型的返回，分析为何没有终止。

**Q: log.txt 太大了怎么办**

A: 日志模块内置自动轮转 —— 超过 5MB 自动备份为 `log.txt.YYYYMMDD_HHMMSS.bak` 并新建文件。也可手动删除旧日志。

**Q: 想实时看到日志内容（终端同步输出）**

A: 设置环境变量 `AGENT_LOG_ECHO=1` 即可。

**Q: 想用其他兼容 OpenAI 的模型（如本地 vLLM）**

A: 修改 `DEEPSEEK_BASE_URL` 和 `DEEPSEEK_MODEL` 即可:
```bash
set DEEPSEEK_BASE_URL=http://localhost:8000/v1
set DEEPSEEK_MODEL=your-model-name
```

**Q: MCP 工具没有出现在可用工具列表中**

A: 检查以下几点:
1. `config.MCP_ENABLED` 是否为 True（环境变量 `AGENT_MCP_ENABLED=0` 会禁用）
2. MCP 服务器是否能独立运行: `python MCP/server.py`
3. `config.MCP_SERVERS` 中的 command 和 args 是否正确
4. 启动时终端是否显示 `[✓ MCP] 已连接 N 台服务器`
5. 查看 `log.txt` 中 "MCP 集成" 相关日志

**Q: 如何添加更多 MCP 服务器**

A: 在 `config.py` 的 `MCP_SERVERS` 列表中添加:
```python
{
    "name": "my_server",
    "command": "python",
    "args": ["path/to/server.py"],
}
```
重启 Agent 即可自动发现新服务器的工具。

**Q: Web UI 启动后浏览器无法访问**

A: 检查:
1. 终端是否显示 "Running on http://..."
2. 端口 5000 是否被占用（可设 `FLASK_PORT=8080` 换端口）
3. 防火墙是否拦截
4. 如部署到服务器，确保 host 设为 `0.0.0.0`

**Q: Web UI 回复很慢或卡住**

A: Web UI 依赖 DeepSeek API 响应速度，可通过以下方式排查:
1. 查看后台终端 `log.txt` 确认 API 调用是否正常
2. 在 CLI 模式测试相同请求确认 API 可用
3. 检查网络代理设置（`DEEPSEEK_BASE_URL`）
