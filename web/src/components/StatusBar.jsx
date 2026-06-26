import React, { useState, useEffect, useRef } from 'react'
import { fetchStatus } from '../api'

function fmtK(n) {
  if (n == null) return '—'
  if (n >= 1000) return (n / 1000).toFixed(1) + 'K'
  return String(n)
}

export default function StatusBar({ initialMeta, onStatus }) {
  const [live, setLive] = useState(null)
  const onStatusRef = useRef(onStatus)
  onStatusRef.current = onStatus

  // initialMeta 变化时（切换会话）：清除旧 live，让快照立即生效
  useEffect(() => {
    setLive(null)
  }, [initialMeta])

  // 合并：live 实时数据优先，否则回退 initialMeta
  const status = live || initialMeta

  useEffect(() => {
    let alive = true
    function poll() {
      fetchStatus()
        .then(s => {
          if (!alive) return
          setLive(s)
          onStatusRef.current?.(s)
        })
        .catch(() => {
          if (!alive) return
          const fallback = { connected: false, base_url: '—' }
          setLive(fallback)
          onStatusRef.current?.(fallback)
        })
    }
    poll()
    const iv = setInterval(poll, 5000)
    return () => { alive = false; clearInterval(iv) }
  }, [])  // 只在 mount 时启动轮询，避免反复重置

  if (!status) return null

  const pct = status.max_context > 0
    ? Math.min(100, Math.round((status.context_tokens / status.max_context) * 100))
    : 0

  return (
    <div className="status-bar">
      <span className="status-item">
        <span className={`status-dot${status.connected ? ' on' : ' off'}`} />
        {status.connected ? status.base_url : '未连接'}
      </span>
      <span className="status-item">
        🪙 {fmtK(status.total_tokens)} tokens
      </span>
      <span className="status-item">
        📊 {fmtK(status.context_tokens)} / {fmtK(status.max_context)}
        <span className="ctx-bar"><span className="ctx-fill" style={{ width: `${pct}%` }} /></span>
      </span>
      <span className="status-item">
        🧠 {status.model || '—'}  |  temp={status.temperature ?? '—'}  |  max_tok={fmtK(status.max_tokens)}
      </span>
    </div>
  )
}
