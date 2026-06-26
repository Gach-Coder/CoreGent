import React, { useState, useEffect } from 'react'
import { fetchSessions, createSession, deleteSession as apiDeleteSession } from '../api'

export default function Sidebar({
  activeSessionId,
  onSwitchSession,
  onNewSession,
  onDeleteSession,
  onOpenSettings,
  refreshTrigger,
}) {
  const [sessions, setSessions] = useState([])
  const [editingId, setEditingId] = useState(null)
  const [editName, setEditName] = useState('')

  // 加载会话列表
  useEffect(() => {
    fetchSessions()
      .then(list => setSessions(list))
      .catch(() => {})
  }, [refreshTrigger])

  async function handleNew() {
    try {
      const id = Date.now().toString(36)
      const { id: sid } = await createSession(id, `会话 ${sessions.length + 1}`)
      // 刷新列表后通知 App 切换到新会话
      const list = await fetchSessions()
      setSessions(list)
      onNewSession(sid)
    } catch { /* ignore */ }
  }

  function handleSwitch(id) {
    onSwitchSession(id)
  }

  async function handleDelete(id, e) {
    e.stopPropagation()
    try {
      await apiDeleteSession(id)
      const list = await fetchSessions()
      setSessions(list)
      onDeleteSession(id)
    } catch { /* ignore */ }
  }

  function startRename(id, name, e) {
    e.stopPropagation()
    setEditingId(id)
    setEditName(name)
  }

  async function commitRename(id) {
    const name = editName.trim() || '未命名'
    try {
      await fetch(`/sessions/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
      })
      const list = await fetchSessions()
      setSessions(list)
    } catch { /* ignore */ }
    setEditingId(null)
  }

  function handleRenameKey(e, id) {
    if (e.key === 'Enter') commitRename(id)
    if (e.key === 'Escape') setEditingId(null)
  }

  return (
    <div className="sidebar">
      <div className="sidebar-header">
        <span className="sidebar-title">💬 会话</span>
        <button className="sidebar-new-btn" onClick={handleNew} title="新建会话">+</button>
      </div>

      <div className="session-list">
        {sessions.map(s => (
          <div
            key={s.id}
            className={`session-item${s.id === activeSessionId ? ' active' : ''}`}
            onClick={() => handleSwitch(s.id)}
          >
            {editingId === s.id ? (
              <input
                className="session-rename-input"
                value={editName}
                onChange={e => setEditName(e.target.value)}
                onBlur={() => commitRename(s.id)}
                onKeyDown={e => handleRenameKey(e, s.id)}
                onClick={e => e.stopPropagation()}
                autoFocus
              />
            ) : (
              <span
                className="session-name"
                onDoubleClick={e => startRename(s.id, s.name, e)}
              >
                {s.name}
              </span>
            )}
            <button
              className="session-delete-btn"
              onClick={e => handleDelete(s.id, e)}
              title="删除会话"
            >
              ×
            </button>
          </div>
        ))}
        {sessions.length === 0 && (
          <div className="session-empty">暂无会话，点击 + 新建</div>
        )}
      </div>

      <div className="sidebar-footer">
        <button className="sidebar-settings-btn" onClick={onOpenSettings}>
          ⚙ 设置
        </button>
      </div>
    </div>
  )
}
