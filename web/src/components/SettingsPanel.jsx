import React, { useState, useEffect } from 'react'
import { fetchMcpConfig, fetchSkills } from '../api'

export default function SettingsPanel({ isOpen, onClose, theme, onThemeChange }) {
  const [mcp, setMcp] = useState(null)
  const [skills, setSkills] = useState(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!isOpen) return
    setLoading(true)
    Promise.all([
      fetchMcpConfig().catch(() => ({ enabled: false, servers: [], prefix: '' })),
      fetchSkills().catch(() => ({ tools: [], count: 0 })),
    ]).then(([mcpData, skillsData]) => {
      setMcp(mcpData)
      setSkills(skillsData)
      setLoading(false)
    })
  }, [isOpen])

  if (!isOpen) return null

  return (
    <>
      <div className="settings-overlay" onClick={onClose} />
      <div className="settings-panel">
        <div className="settings-header">
          <h2>⚙ 设置</h2>
          <button className="settings-close-btn" onClick={onClose}>×</button>
        </div>

        <div className="settings-body">
          {/* ── 主题 ── */}
          <section className="settings-section">
            <h3>🎨 主题</h3>
            <div className="theme-switch">
              <button
                className={`theme-btn${theme === 'dark' ? ' active' : ''}`}
                onClick={() => onThemeChange('dark')}
              >
                🌙 深色
              </button>
              <button
                className={`theme-btn${theme === 'light' ? ' active' : ''}`}
                onClick={() => onThemeChange('light')}
              >
                ☀ 浅色
              </button>
            </div>
          </section>

          {/* ── MCP 配置 ── */}
          <section className="settings-section">
            <h3>🔌 MCP 服务器</h3>
            {loading ? (
              <div className="settings-loading">加载中…</div>
            ) : mcp ? (
              <>
                <div className="settings-field">
                  <span className="field-label">状态</span>
                  <span className={`field-value badge ${mcp.enabled ? 'on' : 'off'}`}>
                    {mcp.enabled ? '已启用' : '已禁用'}
                  </span>
                </div>
                <div className="settings-field">
                  <span className="field-label">工具前缀</span>
                  <code className="field-value">{mcp.prefix}</code>
                </div>
                {mcp.servers.length > 0 ? (
                  <div className="mcp-server-list">
                    {mcp.servers.map((s, i) => (
                      <div key={i} className="mcp-server-item">
                        <div className="mcp-server-name">{s.name}</div>
                        <code className="mcp-server-cmd">{s.command} {s.args?.join(' ')}</code>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="settings-empty">未配置 MCP 服务器</div>
                )}
              </>
            ) : null}
          </section>

          {/* ── Skills / 工具 ── */}
          <section className="settings-section">
            <h3>🛠 工具 / Skills</h3>
            {loading ? (
              <div className="settings-loading">加载中…</div>
            ) : skills ? (
              <>
                <div className="settings-field">
                  <span className="field-label">总数</span>
                  <span className="field-value">{skills.count}</span>
                </div>
                <div className="skills-list">
                  {skills.tools.map(t => (
                    <div key={t.name} className="skill-item">
                      <div className="skill-name">
                        {t.name}
                        <span className={`skill-badge ${t.source}`}>
                          {t.source === 'mcp' ? 'MCP' : '内置'}
                        </span>
                      </div>
                      <div className="skill-desc">{t.description}</div>
                    </div>
                  ))}
                </div>
              </>
            ) : null}
          </section>
        </div>
      </div>
    </>
  )
}
