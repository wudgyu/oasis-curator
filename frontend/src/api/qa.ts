import request from '@/utils/request'
import { streamSse } from '@/utils/sse'
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
  await streamSse(
    '/api/qa/ask/stream',
    {
      question: payload.question,
      conversation_id: payload.conversationId ?? null,
      doc_id: payload.docId ?? null,
    },
    (event, data) => {
      switch (event) {
        case 'meta':
          handlers.onMeta?.({
            conversationId: String(data.conversation_id ?? ''),
            retrievedCount: Number(data.retrieved_count ?? 0),
            sources: ((data.reranked as RawMessage['sources']) ?? []).map(mapSource),
          })
          break
        case 'token':
          handlers.onToken?.(String(data.text ?? ''))
          break
        case 'done':
          handlers.onDone?.({
            answer: String(data.answer ?? ''),
            refused: Boolean(data.refused),
            citations: (data.citations as string[]) ?? [],
            provider: String(data.provider ?? ''),
          })
          break
        case 'error':
          handlers.onError?.(String(data.message ?? '生成失败'))
          break
        default:
          break
      }
    },
    signal,
  )
}
