import React, { useState } from 'react'

export default function ToolCallCard({ name, args, result }) {
  const [expanded, setExpanded] = useState(false)

  let argsDisplay = ''
  try {
    argsDisplay = JSON.stringify(JSON.parse(args), null, 2)
  } catch {
    argsDisplay = args
  }

  return (
    <div className={`tool-call${expanded ? ' expanded' : ''}`}>
      <div className="tool-header" onClick={() => setExpanded(v => !v)}>
        <span className="tool-name">🔧 {name}</span>
        <span className="tool-toggle">▶</span>
      </div>
      <div className="tool-body">
        <div className="tool-args">{argsDisplay}</div>
        {result && (
          <div className="tool-result">
            {result.length > 500 ? result.slice(0, 500) + '…' : result}
          </div>
        )}
      </div>
    </div>
  )
}
