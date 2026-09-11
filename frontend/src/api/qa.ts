import request from '@/utils/request'
import type {
  ConversationDetail,
  ConversationItem,
  MessageSource,
  StreamAskPayload,
} from '@/types'

/**
 * 文档问答 API
 * 对接后端 /api/qa
 *
 * 流式问答使用 fetch + ReadableStream（EventSource 不支持自定义请求头与 POST），
 * 因此这里不走 Axios 实例，需自行注入 Token 并处理 401。
 */

interface RawConversation {
  id: string
  title: string
  message_count: number
  created_at: string
  updated_at: string
}

interface RawMessage {
  id: string
  role: string
  content: string
  refused: boolean
  citations: string[]
  sources: Array<{
    score: number
    text: string
    source_file: string
    chunk_index: number
    page: number | null
  }>
  created_at: string
}

interface RawConversationDetail {
  id: string
  title: string
  created_at: string
  updated_at: string
  messages: RawMessage[]
}

function mapSource(raw: RawMessage['sources'][number]): MessageSource {
  return {
    score: raw.score,
    text: raw.text,
    sourceFile: raw.source_file,
    chunkIndex: raw.chunk_index,
    page: raw.page,
  }
}

function mapConversation(raw: RawConversation): ConversationItem {
  return {
    id: raw.id,
    title: raw.title,
    messageCount: raw.message_count,
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
  }
}

/** 会话列表（按更新时间倒序） */
export async function fetchConversations(): Promise<ConversationItem[]> {
  const { data } = await request.get<RawConversation[]>('/qa/conversations')
  return data.map(mapConversation)
}

/** 会话详情（含全部消息与引用原文） */
export async function fetchConversationDetail(id: string): Promise<ConversationDetail> {
  const { data } = await request.get<RawConversationDetail>(`/qa/conversations/${id}`)
  return {
    id: data.id,
    title: data.title,
    createdAt: data.created_at,
    updatedAt: data.updated_at,
    messages: data.messages.map((m) => ({
      id: m.id,
      role: m.role === 'assistant' ? 'assistant' : 'user',
      content: m.content,
      refused: m.refused,
      citations: m.citations ?? [],
      sources: (m.sources ?? []).map(mapSource),
      createdAt: m.created_at,
    })),
  }
}

/** 重命名会话 */
export async function renameConversation(id: string, title: string): Promise<ConversationItem> {
  const { data } = await request.patch<RawConversation>(`/qa/conversations/${id}`, { title })
  return mapConversation(data)
}

/** 删除会话（级联删除消息） */
export async function deleteConversation(id: string): Promise<void> {
  await request.delete(`/qa/conversations/${id}`)
}

// ---------------------------------------------------------------------------
// 流式问答
// ---------------------------------------------------------------------------

export interface StreamHandlers {
  /** 检索完成：返回重排序候选块与会话 ID（新会话时由后端创建） */
  onMeta?: (payload: { conversationId: string; retrievedCount: number; sources: MessageSource[] }) => void
  /** 逐 token 增量文本 */
  onToken?: (text: string) => void
  /** 生成结束：完整答案、引用与拒答标记 */
  onDone?: (payload: {
    answer: string
    refused: boolean
    citations: string[]
    provider: string
  }) => void
  /** 流内错误（后端生成失败） */
  onError?: (message: string) => void
}

/** 解析单个 SSE 帧（event: X \n data: {...}） */
function handleFrame(frame: string, handlers: StreamHandlers): void {
  let eventName = ''
  let dataLine = ''
  for (const line of frame.split('\n')) {
    if (line.startsWith('event: ')) eventName = line.slice(7).trim()
    else if (line.startsWith('data: ')) dataLine = line.slice(6)
  }
  if (!eventName || !dataLine) return

  const payload = JSON.parse(dataLine)
  switch (eventName) {
    case 'meta':
      handlers.onMeta?.({
        conversationId: payload.conversation_id,
        retrievedCount: payload.retrieved_count,
        sources: (payload.reranked ?? []).map(mapSource),
      })
      break
    case 'token':
      handlers.onToken?.(payload.text)
      break
    case 'done':
      handlers.onDone?.({
        answer: payload.answer,
        refused: payload.refused,
        citations: payload.citations ?? [],
        provider: payload.provider ?? '',
      })
      break
    case 'error':
      handlers.onError?.(payload.message ?? '生成失败')
      break
    default:
      break
  }
}

/**
 * 发起流式问答
 *
 * 后端 SSE 事件：meta（检索/重排序结果）→ token（逐字）→ done（引用与拒答）
 */
export async function askStream(
  payload: StreamAskPayload,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const token = localStorage.getItem('token')
  const response = await fetch('/api/qa/ask/stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({
      question: payload.question,
      conversation_id: payload.conversationId ?? null,
      doc_id: payload.docId ?? null,
    }),
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
      const body = await response.json()
      if (typeof body?.detail === 'string') detail = body.detail
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
        const frame = buffer.slice(0, boundary)
        buffer = buffer.slice(boundary + 2)
        if (frame.trim()) handleFrame(frame, handlers)
        boundary = buffer.indexOf('\n\n')
      }
    }
  } finally {
    reader.releaseLock()
  }
}
