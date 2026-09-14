/**
 * SSE（Server-Sent Events）传输层
 *
 * 使用 fetch + ReadableStream 而非 EventSource：
 * EventSource 不支持自定义请求头，也无法发送 POST 请求体。
 *
 * 统一处理：Token 注入、401 跳转登录、错误信息提取与 SSE 分帧，
 * 供问答流式接口与 Agent 执行流共用。
 */

/** 单帧回调：event 为事件名，data 为解析后的 JSON */
export type SseFrameHandler = (event: string, data: Record<string, unknown>) => void

/** 解析单帧文本（`event: X` + `data: {...}`） */
function parseFrame(frame: string): { event: string; data: Record<string, unknown> } | null {
  let event = ''
  let dataLine = ''
  for (const line of frame.split('\n')) {
    if (line.startsWith('event: ')) event = line.slice(7).trim()
    else if (line.startsWith('data: ')) dataLine = line.slice(6)
  }
  if (!event || !dataLine) return null
  try {
    return { event, data: JSON.parse(dataLine) }
  } catch {
    return null
  }
}

/**
 * 发起 POST 请求并以 SSE 方式消费响应
 *
 * @param url 接口路径（相对路径，走 Vite 代理）
 * @param body 请求体
 * @param onFrame 每帧回调
 * @param signal 中断信号（用户点击停止时使用）
 */
export async function streamSse(
  url: string,
  body: unknown,
  onFrame: SseFrameHandler,
  signal?: AbortSignal,
): Promise<void> {
  const token = localStorage.getItem('token')
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
    signal,
  })

  if (response.status === 401) {
    // 与 Axios 拦截器保持一致：清除登录态并跳转登录页
    localStorage.removeItem('token')
    window.location.hash = '#/login'
    throw new Error('登录已过期，请重新登录')
  }
  if (!response.ok || !response.body) {
    let detail = `请求失败 (${response.status})`
    try {
      const payload = await response.json()
      if (typeof payload?.detail === 'string') detail = payload.detail
    } catch {
      // 非 JSON 响应，保留默认提示
    }
    throw new Error(detail)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  try {
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      // SSE 帧以空行分隔
      let boundary = buffer.indexOf('\n\n')
      while (boundary >= 0) {
        const raw = buffer.slice(0, boundary)
        buffer = buffer.slice(boundary + 2)
        if (raw.trim()) {
          const frame = parseFrame(raw)
          if (frame) onFrame(frame.event, frame.data)
        }
        boundary = buffer.indexOf('\n\n')
      }
    }
  } finally {
    reader.releaseLock()
  }
}
