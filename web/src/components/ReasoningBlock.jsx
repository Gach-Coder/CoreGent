import React, { useState } from 'react'

export default function ReasoningBlock({ text, isStreaming }) {
  const [expanded, setExpanded] = useState(false)

  if (!text && !isStreaming) return null

  const isFinal = !isStreaming

  return (
    <div className={`reasoning-card${isStreaming ? ' streaming' : ''}`}>
      <div
        className={`reasoning-card-header${isFinal ? ' clickable' : ''}`}
        onClick={() => isFinal && setExpanded(v => !v)}
      >
        <span className="reasoning-card-icon">🧠</span>
        <span className="reasoning-card-label">思考过程</span>
        {isStreaming && <span className="reasoning-card-dot" />}
        {isFinal && (
          <span className={`reasoning-card-arrow${expanded ? ' open' : ''}`}>▶</span>
        )}
      </div>
      {(isStreaming || expanded) && (
        <div className="reasoning-card-text">{text || '…'}</div>
      )}
    </div>
  )
}
