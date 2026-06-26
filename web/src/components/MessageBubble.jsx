import React, { useMemo } from 'react'

function renderMarkdown(text) {
  if (!text) return ''
  let html = escapeHtml(text)
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>')
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>')
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  html = html.replace(/^[ \t]*[-*] (.+)$/gm, '<li>$1</li>')
  html = html.replace(/((?:<li>.*<\/li>\n?)+)/g, '<ul>$1</ul>')
  html = html.replace(/^[ \t]*\d+\. (.+)$/gm, '<li>$1</li>')
  html = html.replace(/\n\n/g, '</p><p>')
  html = '<p>' + html + '</p>'
  html = html.replace(/<p>\s*<\/p>/g, '')
  return html
}

function escapeHtml(str) {
  const div = document.createElement('div')
  div.textContent = str
  return div.innerHTML
}

export default function MessageBubble({ type, role, content, isStreaming }) {
  const html = useMemo(() => renderMarkdown(content || ''), [content])

  // 兼容旧格式：role='user' 或 type='user'
  if (type === 'user' || role === 'user') {
    return <div className="msg user">{content}</div>
  }

  // agent content bubble
  return (
    <div className={`msg agent${isStreaming ? ' streaming' : ''}`}>
      {isStreaming
        ? <div>{content || ''}</div>
        : <div dangerouslySetInnerHTML={{ __html: html }} />
      }
    </div>
  )
}
