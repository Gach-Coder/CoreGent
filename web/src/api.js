// ============================================================
// API helpers —— fetch REST + SSE streaming
// ============================================================

/**
 * Fetch model info from /health
 */
export async function fetchHealth() {
  const resp = await fetch('/health')
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
  return resp.json()
}

/**
 * Reset chat history
 */
export async function resetChat() {
  const resp = await fetch('/reset', { method: 'POST' })
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
  return resp.json()
}

/**
 * Stream a chat message via SSE.
 *
 * @param {string} message  - user input
 * @param {object} callbacks - { onReasoning, onContent, onToolCall, onToolResult, onError, onDone }
 * @returns {Promise<string>} final answer text
 */
export async function streamChat(message, callbacks) {
  const resp = await fetch('/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
  })

  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}))
    throw new Error(err.error || `HTTP ${resp.status}`)
  }

  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let finalText = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    // Last element may be incomplete
    buffer = ''

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i]
      if (!line.startsWith('data: ')) continue

      try {
        const event = JSON.parse(line.slice(6))
        const { type, data } = event

        switch (type) {
          case 'reasoning':
            callbacks.onReasoning?.(data.text)
            break
          case 'content':
            callbacks.onContent?.(data.text)
            break
          case 'tool_call':
            callbacks.onToolCall?.(data.name, data.arguments)
            break
          case 'tool_result':
            callbacks.onToolResult?.(data.name, data.result)
            break
          case 'done':
            finalText = data.text || ''
            break
          case 'error':
            callbacks.onError?.(data.message)
            break
        }
      } catch {
        // Incomplete JSON — put it back in buffer
        buffer = line + '\n' + lines.slice(i + 1).join('\n')
        break
      }
    }
  }

  callbacks.onDone?.(finalText)
  return finalText
}

/**
 * Fetch MCP server configuration
 */
export async function fetchMcpConfig() {
  const resp = await fetch('/mcp')
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
  return resp.json()
}

/**
 * Fetch registered tools / skills
 */
export async function fetchSkills() {
  const resp = await fetch('/skills')
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
  return resp.json()
}

/**
 * Fetch runtime status (connection, tokens, context, model)
 */
export async function fetchStatus() {
  const resp = await fetch('/status')
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
  return resp.json()
}

// ============================================================
// Session API
// ============================================================

export async function fetchSessions() {
  const resp = await fetch('/sessions')
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
  return resp.json()
}

export async function createSession(id, name) {
  const resp = await fetch('/sessions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id, name, createdAt: Date.now() }),
  })
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
  return resp.json()
}

export async function getSession(id) {
  const resp = await fetch(`/sessions/${id}`)
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
  return resp.json()
}

export async function saveSession(id, messages, meta) {
  const resp = await fetch(`/sessions/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ messages, meta }),
  })
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
}

export async function deleteSession(id) {
  const resp = await fetch(`/sessions/${id}`, { method: 'DELETE' })
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
}
