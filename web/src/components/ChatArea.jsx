import React, { useRef, useEffect, useCallback } from 'react'
import MessageBubble from './MessageBubble'
import ReasoningBlock from './ReasoningBlock'
import ToolCallCard from './ToolCallCard'

export default function ChatArea({ messages, isStreaming }) {
  const ref = useRef(null)
  const prevLenRef = useRef(0)
  const blockUntilRef = useRef(0)  // 用户点击折叠卡后短暂禁止滚动

  const isNearBottom = useCallback(() => {
    const el = ref.current
    if (!el) return true
    return el.scrollHeight - el.scrollTop - el.clientHeight < 80
  }, [])

  // 点击折叠卡（思考/工具）时暂停自动滚动 600ms
  function handleChatClick(e) {
    const card = e.target.closest('.reasoning-card-header, .tool-header')
    if (card) blockUntilRef.current = Date.now() + 600
  }

  useEffect(() => {
    const len = messages.length
    if (Date.now() < blockUntilRef.current) return
    const shouldScroll = (isStreaming || len > prevLenRef.current) && isNearBottom()
    if (shouldScroll) {
      requestAnimationFrame(() => {
        if (ref.current) {
          ref.current.scrollTop = ref.current.scrollHeight
        }
      })
    }
    prevLenRef.current = len
  }, [messages, isStreaming, isNearBottom])

  if (messages.length === 0) {
    return (
      <div className="chat-area" ref={ref}>
        <div className="empty-state">
          <div className="icon">💬</div>
          <div>向 CoreGent 发送消息开始对话</div>
          <div className="hints">
            试试这些：<br />
            • 列出当前目录的所有文件<br />
            • 帮我创建一个 hello.py<br />
            • 搜索所有 .py 文件
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="chat-area" ref={ref} onClick={handleChatClick}>
      {messages.map(msg => {
        switch (msg.type) {
          case 'reasoning':
            return (
              <ReasoningBlock
                key={msg.key}
                text={msg.text}
                isStreaming={msg.isStreaming}
              />
            )
          case 'tool_call':
            return (
              <ToolCallCard
                key={msg.key}
                name={msg.name}
                args={msg.args}
                result={msg.result}
              />
            )
          default: {
            // 兼容旧格式（role 字段）
            const msgType = msg.type || (msg.role === 'user' ? 'user' : 'agent')
            return (
              <MessageBubble
                key={msg.key}
                type={msgType}
                role={msg.role}
                content={msg.content}
                isStreaming={msg.isStreaming}
              />
            )
          }
        }
      })}
    </div>
  )
}
