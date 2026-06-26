import React, { useReducer, useRef, useEffect, useCallback, useState } from 'react'
import Header from './components/Header'
import ChatArea from './components/ChatArea'
import InputArea from './components/InputArea'
import Sidebar from './components/Sidebar'
import SettingsPanel from './components/SettingsPanel'
import StatusBar from './components/StatusBar'
import { streamChat, fetchHealth, resetChat as apiReset, fetchSessions, createSession, getSession, saveSession } from './api'

// ============================================================
// Messages reducer
// ============================================================

const initialState = { messages: [], reasoningKey: null, agentKey: null }

function finalizeMsg(m, key) { return m.key === key ? { ...m, isStreaming: false } : m }

function reducer(state, action) {
  switch (action.type) {

    case 'ADD_USER':
      return {
        ...state,
        messages: [...state.messages, {
          type: 'user', content: action.text, key: action.key,
        }],
      }

    case 'ENSURE_REASONING': {
      if (state.reasoningKey) return state
      if (state.messages.some(m => m.key === action.key)) return state
      return {
        ...state,
        reasoningKey: action.key,
        messages: [...state.messages, {
          type: 'reasoning', text: '', isStreaming: true, key: action.key,
        }],
      }
    }

    case 'ENSURE_AGENT': {
      if (state.agentKey) return state
      if (state.messages.some(m => m.key === action.key)) return state
      return {
        ...state,
        agentKey: action.key,
        messages: [...state.messages, {
          type: 'agent', content: '', isStreaming: true, key: action.key,
        }],
      }
    }

    case 'APPEND_REASONING':
      return {
        ...state,
        messages: state.messages.map(m =>
          m.key === state.reasoningKey
            ? { ...m, text: (m.text || '') + action.text }
            : m
        ),
      }

    case 'APPEND_CONTENT':
      return {
        ...state,
        messages: state.messages.map(m =>
          m.key === state.agentKey
            ? { ...m, content: (m.content || '') + action.text }
            : m
        ),
      }

    case 'ADD_TOOL_CALL': {
      let msgs = state.messages
      if (state.reasoningKey) msgs = msgs.map(m => finalizeMsg(m, state.reasoningKey))
      if (state.agentKey)    msgs = msgs.map(m => finalizeMsg(m, state.agentKey))
      return {
        reasoningKey: null,
        agentKey: null,
        messages: [...msgs, {
          type: 'tool_call', name: action.name, args: action.args,
          result: '', key: action.key,
        }],
      }
    }

    case 'SET_TOOL_RESULT':
      return {
        ...state,
        messages: state.messages.map(m =>
          m.key === action.key
            ? { ...m, result: action.result }
            : m
        ),
      }

    case 'FINALIZE': {
      let msgs = state.messages
      if (state.reasoningKey) msgs = msgs.map(m => finalizeMsg(m, state.reasoningKey))
      if (state.agentKey)    msgs = msgs.map(m => finalizeMsg(m, state.agentKey))
      return { reasoningKey: null, agentKey: null, messages: msgs }
    }

    case 'SET_ERROR': {
      let msgs = state.messages.map(m =>
        m.isStreaming ? { ...m, content: m.content || '', isStreaming: false } : m
      )
      return { reasoningKey: null, agentKey: null, messages: msgs }
    }

    case 'LOAD':
      return { messages: action.messages, reasoningKey: null, agentKey: null }

    case 'RESET':
      return initialState

    default:
      return state
  }
}

// ============================================================
// App
// ============================================================

const THEME_KEY = 'coregent_theme'

function loadTheme() {
  try { return localStorage.getItem(THEME_KEY) || 'dark' }
  catch { return 'dark' }
}

function saveTheme(theme) {
  localStorage.setItem(THEME_KEY, theme)
  document.documentElement.dataset.theme = theme
}

export default function App() {
  const [state, dispatch] = useReducer(reducer, initialState)
  const [model, setModel] = useState('...')
  const [theme, setThemeState] = useState(loadTheme)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [activeSessionId, setActiveSessionId] = useState(null)
  const [refreshTrigger, setRefreshTrigger] = useState(0)
  const [sessionMeta, setSessionMeta] = useState(null)  // { total_tokens, context_tokens, max_context, model, temperature, max_tokens }
  const statusRef = useRef(null)  // 最新 /status 快照
  const keyRef = useRef(0)
  const toolKeyRef = useRef(null)

  const nextKey = useCallback(() => `k-${++keyRef.current}`, [])

  // 初始化：从服务器加载会话列表，自动选中第一个
  const initRef = useRef(false)
  useEffect(() => {
    if (initRef.current) return
    initRef.current = true
    fetchSessions().then(async list => {
      if (list.length === 0) {
        // 首次使用：创建默认会话
        const id = Date.now().toString(36)
        await createSession(id, '会话 1')
        setActiveSessionId(id)
        setRefreshTrigger(n => n + 1)
      } else {
        const first = list[0]
        setActiveSessionId(first.id)
        setRefreshTrigger(n => n + 1)
        try {
          const doc = await getSession(first.id)
          if (doc.messages?.length) dispatch({ type: 'LOAD', messages: doc.messages })
          if (doc.meta) setSessionMeta(doc.meta)
        } catch { /* ignore */ }
      }
    }).catch(() => {})
  }, [])

  // Apply theme on mount
  useEffect(() => {
    document.documentElement.dataset.theme = theme
  }, [])

  function handleThemeChange(t) {
    setThemeState(t)
    saveTheme(t)
  }

  // Fetch model name on mount
  useEffect(() => {
    fetchHealth()
      .then(d => setModel(d.model || '...'))
      .catch(() => setModel('?'))
  }, [])

  // Auto-save current session to server (debounced)
  const saveRef = useRef(null)
  useEffect(() => {
    if (!activeSessionId) return
    clearTimeout(saveRef.current)
    saveRef.current = setTimeout(() => {
      const meta = statusRef.current
      if (meta) setSessionMeta(meta)
      saveSession(activeSessionId, state.messages, meta).catch(() => {})
    }, 500)
    return () => clearTimeout(saveRef.current)
  }, [state.messages, activeSessionId])

  function handleNewSession(id) {
    setActiveSessionId(id)
    setRefreshTrigger(n => n + 1)
    statusRef.current = null  // 清除旧会话的 token 快照
    setSessionMeta(null)
    apiReset()
    dispatch({ type: 'RESET' })
  }

  function handleSwitchSession(id) {
    setActiveSessionId(id)
    statusRef.current = null  // 清除旧会话的 token 快照
    apiReset()
    getSession(id).then(doc => {
      if (doc.messages?.length) {
        dispatch({ type: 'LOAD', messages: doc.messages })
      } else {
        dispatch({ type: 'RESET' })
      }
      setSessionMeta(doc.meta || null)
    }).catch(() => {
      dispatch({ type: 'RESET' })
      setSessionMeta(null)
    })
  }

  function handleDeleteSession(id) {
    if (id === activeSessionId) {
      fetchSessions().then(list => {
        const remaining = list.filter(s => s.id !== id)
        const next = remaining[0]
        if (next) {
          setActiveSessionId(next.id)
          statusRef.current = null
          apiReset()
          getSession(next.id).then(doc => {
            dispatch(doc.messages?.length ? { type: 'LOAD', messages: doc.messages } : { type: 'RESET' })
            setSessionMeta(doc.meta || null)
          }).catch(() => dispatch({ type: 'RESET' }))
        } else {
          setActiveSessionId(null)
          apiReset()
          dispatch({ type: 'RESET' })
          setSessionMeta(null)
        }
      }).catch(() => {})
    }
  }

  // Send message handler
  async function handleSend(text) {
    if (!activeSessionId) {
      const id = Date.now().toString(36)
      await createSession(id, text.slice(0, 30))
      statusRef.current = null  // 新会话从零开始
      setSessionMeta(null)
      setActiveSessionId(id)
      setRefreshTrigger(n => n + 1)
    }

    dispatch({ type: 'ADD_USER', text, key: nextKey() })

    let reasoningKey = nextKey()
    let agentKey = null  // 延迟创建：收到首个 content 时才创建消息框
    dispatch({ type: 'ENSURE_REASONING', key: reasoningKey })

    try {
      await streamChat(text, {
        onReasoning(text) {
          dispatch({ type: 'APPEND_REASONING', text })
        },
        onContent(text) {
          if (!agentKey) {
            agentKey = nextKey()
            dispatch({ type: 'ENSURE_AGENT', key: agentKey })
          }
          dispatch({ type: 'APPEND_CONTENT', text })
        },
        onToolCall(name, args) {
          toolKeyRef.current = nextKey()
          dispatch({ type: 'ADD_TOOL_CALL', name, args, key: toolKeyRef.current })
          reasoningKey = nextKey()
          agentKey = null  // 下一轮同样延迟
          dispatch({ type: 'ENSURE_REASONING', key: reasoningKey })
        },
        onToolResult(_name, result) {
          if (toolKeyRef.current) {
            dispatch({ type: 'SET_TOOL_RESULT', key: toolKeyRef.current, result })
          }
        },
        onError(message) {
          dispatch({ type: 'SET_ERROR', message })
        },
        onDone() {
          dispatch({ type: 'FINALIZE' })
        },
      })
    } catch (err) {
      dispatch({ type: 'SET_ERROR', message: err.message })
    }
  }

  async function handleReset() {
    await apiReset()
    dispatch({ type: 'RESET' })
  }

  const isStreaming = state.reasoningKey !== null

  return (
    <div className="app">
      <Header model={model} onReset={handleReset} />
      <div className="app-body">
        <Sidebar
          activeSessionId={activeSessionId}
          onSwitchSession={handleSwitchSession}
          onNewSession={handleNewSession}
          onDeleteSession={handleDeleteSession}
          onOpenSettings={() => setSettingsOpen(true)}
          refreshTrigger={refreshTrigger}
        />
        <div className="app-main">
          <ChatArea messages={state.messages} isStreaming={isStreaming} />
          <InputArea onSend={handleSend} disabled={isStreaming} />
        </div>
      </div>
      <StatusBar initialMeta={sessionMeta} onStatus={s => { statusRef.current = s }} />
      <SettingsPanel
        isOpen={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        theme={theme}
        onThemeChange={handleThemeChange}
      />
    </div>
  )
}
