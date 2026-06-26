import React, { useRef, useEffect } from 'react'

export default function InputArea({ onSend, disabled }) {
  const ref = useRef(null)

  // Auto-focus on mount
  useEffect(() => { ref.current?.focus() }, [])

  function handleKey(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  function send() {
    const text = ref.current?.value.trim()
    if (!text || disabled) return
    ref.current.value = ''
    onSend(text)
  }

  return (
    <div className="input-area">
      <textarea
        ref={ref}
        placeholder="输入消息… (Enter 发送，Shift+Enter 换行)"
        rows={1}
        disabled={disabled}
        onKeyDown={handleKey}
      />
      <button
        className="send-btn"
        disabled={disabled}
        onClick={send}
      >
        发送
      </button>
    </div>
  )
}
