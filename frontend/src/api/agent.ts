import type { AgentRun, AgentRunParams, AgentStep } from '@/types'
import request from '@/utils/request'
import { streamSse } from '@/utils/sse'

/**
 * 文档处理 Agent API
 * 对接后端 /api/agent
 *
 * 执行需 admin / manager（Agent 会写入知识库，与文档上传同一权限口径）。
 */

interface RawStep {
  index: number
  tool: string
  args: Record<string, unknown>
  ok: boolean
  elapsed_ms: number
  result_preview: string
  error: string | null
  result: Record<string, unknown>
}

interface RawRun {
  instruction: string
  answer: string
  steps: RawStep[]
  provider: string
  model: string
  mode: string
  iterations: number
  finished: boolean
}

function mapStep(raw: RawStep): AgentStep {
  return {
    index: raw.index,
    tool: raw.tool,
    args: raw.args ?? {},
    ok: raw.ok,
    elapsedMs: raw.elapsed_ms,
    resultPreview: raw.result_preview ?? '',
    error: raw.error,
    result: raw.result ?? {},
  }
}

function mapRun(raw: RawRun): AgentRun {
  return {
    instruction: raw.instruction,
    answer: raw.answer,
    steps: (raw.steps ?? []).map(mapStep),
    provider: raw.provider,
    model: raw.model,
    mode: raw.mode,
    iterations: raw.iterations,
    finished: raw.finished,
  }
}

/** 同步执行（一次性返回完整轨迹） */
export async function runAgent(params: AgentRunParams): Promise<AgentRun> {
  const { data } = await request.post<RawRun>(
    '/agent/run',
    {
      instruction: params.instruction,
      doc_id: params.docId ?? null,
      visibility: params.visibility ?? 'tenant',
      allowed_roles: params.allowedRoles?.join(',') ?? null,
      provider: params.provider ?? null,
      mode: params.mode ?? 'auto',
    },
    { timeout: 300000 }, // Agent 多轮工具调用耗时较长
  )
  return mapRun(data)
}

export interface AgentStreamHandlers {
  /** 每完成一次工具调用 */
  onStep?: (step: AgentStep) => void
  /** 执行结束（含最终答复与完整轨迹） */
  onDone?: (run: AgentRun) => void
  /** 流内错误 */
  onError?: (message: string) => void
}

/** 流式执行：逐步推送工具调用，前端实时展示执行过程 */
export async function runAgentStream(
  params: AgentRunParams,
  handlers: AgentStreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  await streamSse(
    '/api/agent/run/stream',
    {
      instruction: params.instruction,
      doc_id: params.docId ?? null,
      visibility: params.visibility ?? 'tenant',
      allowed_roles: params.allowedRoles?.join(',') ?? null,
      provider: params.provider ?? null,
      mode: params.mode ?? 'auto',
    },
    (event, data) => {
      switch (event) {
        case 'step':
          handlers.onStep?.(mapStep(data as unknown as RawStep))
          break
        case 'done':
          handlers.onDone?.(mapRun(data as unknown as RawRun))
          break
        case 'error':
          handlers.onError?.(String(data.message ?? '执行失败'))
          break
        default:
          break
      }
    },
    signal,
  )
}
