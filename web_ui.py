"""
Web UI 模块 —— Flask + SSE 后端，配合 React 前端。

前端:
  开发 → Vite dev server (:5173) 代理 API 到 Flask (:5003)
  生产 → Flask 直接 serve React build (web/dist/)

API 端点:
  GET  /         → React 聊天页面
  POST /chat     → SSE 流式对话
  POST /reset    → 重置对话历史
  GET  /health   → 健康检查

启动:
    python web_ui.py           # 生产（需先 npm run build）
    开发: 两个终端分别运行 python web_ui.py 和 npm run dev
"""

import json
import os as _os
import queue
import threading

from flask import Flask, request, Response, jsonify, send_from_directory

from agent import Agent
import config


# ============================================================
# Flask 应用
# ============================================================

_PROJECT_DIR = _os.path.dirname(_os.path.abspath(__file__))
_REACT_DIST = _os.path.join(_PROJECT_DIR, "web", "dist")
_SESSIONS_DIR = _os.path.join(_PROJECT_DIR, "sessions")

# 确保 sessions 目录存在
_os.makedirs(_SESSIONS_DIR, exist_ok=True)

def _session_path(sid: str) -> str:
    return _os.path.join(_SESSIONS_DIR, f"{sid}.json")

def _load_session(sid: str) -> dict | None:
    try:
        with open(_session_path(sid), "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None

def _save_session(sid: str, data: dict) -> None:
    with open(_session_path(sid), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

app = Flask(__name__)

# 全局 Agent 实例（线程安全）
_agent: Agent | None = None
_agent_lock = threading.Lock()


def get_agent() -> Agent:
    """获取或创建 Agent 单例。"""
    global _agent
    if _agent is None:
        with _agent_lock:
            if _agent is None:
                _agent = Agent(
                    stream=True,       # Web UI 需要流式
                    log_echo=False,    # 不输出到终端（避免混入 SSE）
                )
    return _agent


# ============================================================
# CORS —— 允许 Vite dev server 跨域访问 API
# ============================================================

@app.after_request
def _add_cors_headers(response):
    response.headers.setdefault("Access-Control-Allow-Origin", "*")
    response.headers.setdefault("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    response.headers.setdefault("Access-Control-Allow-Headers", "Content-Type")
    return response


# ============================================================
# 路由
# ============================================================

@app.route("/")
def index():
    """返回 React 聊天页面。"""
    return send_from_directory(_REACT_DIST, "index.html")


@app.route("/assets/<path:filename>")
def _react_assets(filename):
    """React 静态资源 (JS, CSS)。"""
    return send_from_directory(_os.path.join(_REACT_DIST, "assets"), filename)


@app.route("/chat", methods=["POST"])
def chat():
    """SSE 流式对话端点。

    接收 {"message": "..."}，通过 SSE 逐事件推送回复。
    事件格式: data: {"type": "content"|"tool_call"|"tool_result"|"done"|"error",
                      "data": {...}}
    """
    data = request.get_json(silent=True) or {}
    user_input = (data.get("message") or "").strip()
    if not user_input:
        return jsonify({"error": "消息为空"}), 400

    agent = get_agent()

    # 线程安全队列：agent 线程 → SSE 生成器
    event_queue: queue.Queue = queue.Queue()

    def _stream_callback(event_type: str, data: dict) -> None:
        """Agent 回调 → 入队。"""
        event_queue.put({"type": event_type, "data": data})

    # 在后台线程运行 agent.run()
    result_holder: list = []

    def _run_agent() -> None:
        try:
            result = agent.run(user_input, stream_callback=_stream_callback)
        except Exception as e:
            result = f"运行异常: {e}"
            _stream_callback("error", {"message": str(e)})
        result_holder.append(result)
        event_queue.put(None)  # 哨兵：表示结束

    thread = threading.Thread(target=_run_agent, daemon=True)
    thread.start()

    def generate():
        """SSE 生成器：从队列读取事件并推送。"""
        while True:
            try:
                event = event_queue.get(timeout=0.1)
            except queue.Empty:
                # 检查线程是否已结束
                if not thread.is_alive() and event_queue.empty():
                    break
                continue

            if event is None:  # 哨兵
                break

            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

        # 发送最终结果
        final_text = result_holder[0] if result_holder else ""
        yield f"data: {json.dumps({'type': 'done', 'data': {'text': final_text}}, ensure_ascii=False)}\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.route("/reset", methods=["POST"])
def reset():
    """重置对话历史。"""
    agent = get_agent()
    agent.reset()
    return jsonify({"status": "ok", "message": "对话已重置"})


@app.route("/health", methods=["GET"])
def health():
    """健康检查。"""
    return jsonify({"status": "ok", "model": config.MODEL})


@app.route("/status", methods=["GET"])
def status():
    """返回运行状态：连通、tokens、模型参数。"""
    import concurrent.futures

    connected = False
    api_url = config.BASE_URL
    try:
        agent = get_agent()
        future = concurrent.futures.ThreadPoolExecutor(max_workers=1).submit(
            agent.client.models.list
        )
        future.result(timeout=3)
        connected = True
    except Exception:
        pass

    agent = get_agent()

    return jsonify({
        "connected": connected,
        "base_url": api_url,
        "model": config.MODEL,
        "total_tokens": agent.total_tokens,
        "context_tokens": agent.context_tokens,
        "max_context": agent.max_context,
        "temperature": config.TEMPERATURE,
        "max_tokens": config.MAX_TOKENS,
    })


@app.route("/mcp", methods=["GET"])
def mcp_config():
    """返回 MCP 服务器配置。"""
    servers = []
    for srv in config.MCP_SERVERS:
        servers.append({
            "name": srv.get("name", ""),
            "command": srv.get("command", ""),
            "args": srv.get("args", []),
        })
    return jsonify({
        "enabled": config.MCP_ENABLED,
        "prefix": config.MCP_TOOL_PREFIX,
        "servers": servers,
    })


@app.route("/skills", methods=["GET"])
def skills_list():
    """返回当前注册的工具/Skills 列表。"""
    try:
        from tools import TOOL_DEFINITIONS, TOOL_MAP
        tools = []
        for td in TOOL_DEFINITIONS:
            name = td["function"]["name"]
            desc = td["function"]["description"]
            is_mcp = name.startswith(config.MCP_TOOL_PREFIX)
            tools.append({
                "name": name,
                "description": desc[:120] if desc else "",
                "source": "mcp" if is_mcp else "builtin",
            })
        return jsonify({"tools": tools, "count": len(tools)})
    except Exception as e:
        return jsonify({"tools": [], "count": 0, "error": str(e)})


# ============================================================
# 会话管理 —— JSON 文件存储于 sessions/ 目录
# ============================================================

@app.route("/sessions", methods=["GET"])
def list_sessions():
    """列出所有会话。"""
    sessions = []
    try:
        for fn in sorted(_os.listdir(_SESSIONS_DIR)):
            if fn.endswith(".json"):
                sid = fn[:-5]
                data = _load_session(sid)
                if data:
                    sessions.append({
                        "id": data.get("id", sid),
                        "name": data.get("name", "未命名"),
                        "createdAt": data.get("createdAt", 0),
                    })
    except FileNotFoundError:
        pass
    return jsonify(sessions)


@app.route("/sessions", methods=["POST"])
def create_session():
    """创建新会话。"""
    import time
    data = request.get_json(silent=True) or {}
    sid = data.get("id") or str(int(time.time() * 1000))
    name = data.get("name", "新会话")
    doc = {
        "id": sid,
        "name": name,
        "createdAt": data.get("createdAt", int(time.time() * 1000)),
        "messages": data.get("messages", []),
        "meta": data.get("meta"),
    }
    _save_session(sid, doc)
    return jsonify({"id": sid, "name": name})


@app.route("/sessions/<sid>", methods=["GET"])
def get_session(sid):
    """获取单个会话完整数据。"""
    doc = _load_session(sid)
    if doc is None:
        return jsonify({"error": "会话不存在"}), 404
    return jsonify(doc)


@app.route("/sessions/<sid>", methods=["PUT"])
def update_session(sid):
    """更新会话（保存消息和元数据）。"""
    data = request.get_json(silent=True) or {}
    doc = _load_session(sid)
    if doc is None:
        doc = {"id": sid, "name": data.get("name", "未命名"), "createdAt": data.get("createdAt", 0)}
    if "messages" in data:
        doc["messages"] = data["messages"]
    if "meta" in data:
        doc["meta"] = data["meta"]
    if "name" in data:
        doc["name"] = data["name"]
    _save_session(sid, doc)
    return jsonify({"status": "ok"})


@app.route("/sessions/<sid>", methods=["DELETE"])
def delete_session(sid):
    """删除会话。"""
    try:
        _os.remove(_session_path(sid))
        return jsonify({"status": "ok"})
    except FileNotFoundError:
        return jsonify({"status": "ok"})


# ============================================================
# 入口
# ============================================================

if __name__ == "__main__":
    import sys
    # Windows 下强制 UTF-8 输出（避免 emoji 等字符导致 GBK 编码错误）
    if sys.platform == "win32":
        import io
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace"
        )

    # 端口配置
    _flask_host = _os.environ.get("FLASK_HOST", "127.0.0.1")
    _flask_port = int(_os.environ.get("FLASK_PORT", "5003"))

    print("=" * 54)
    print("  CoreGent Web UI")
    print(f"  Model:     {config.MODEL}")
    print(f"  URL:       http://localhost:{_flask_port}")
    print(f"  Frontend:  React")
    print("=" * 54)

    # 预热 agent（提前连接 MCP 等）
    get_agent()

    app.run(
        host=_flask_host,
        port=_flask_port,
        debug=False,
        threaded=True,
    )
