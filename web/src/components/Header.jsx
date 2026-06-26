import React from 'react'

export default function Header({ model, onReset }) {
  return (
    <div className="header">
      <div className="header-left">
        <span style={{ fontSize: 22 }}>🤖</span>
        <h1>CoreGent</h1>
        <span className="model-tag">{model || '...'}</span>
      </div>
      <button className="btn" onClick={onReset} title="重置对话">
        🔄 重置
      </button>
    </div>
  )
}
