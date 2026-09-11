import request from '@/utils/request'
import type {
  ChunkStrategy,
  DocItem,
  DocUploadParams,
  DocUploadResult,
  DocVisibility,
  PageResult,
  RoleCode,
  SearchChunk,
} from '@/types'

/**
 * 文档管理 API
 * 对接后端 /api/documents
 *
 * 权限（后端校验）：上传/删除需 admin 或 manager；检索所有角色可用。
 * 可见性：上传时指定，检索与列表按可见性过滤（见后端 core/doc_permission.py）。
 */

interface RawDoc {
  id: string
  file_name: string
  file_type: string
  file_size: number
  chunk_count: number
  chunk_strategy: string
  visibility: string
  allowed_roles: string[]
  is_owner: boolean
  created_at: string
}

interface RawPageResult {
  items: RawDoc[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

interface RawUploadResult {
  id: string
  file_name: string
  file_type: string
  char_count: number
  page_count: number
  chunk_count: number
  chunk_strategy: string
}

interface RawSearchChunk {
  text: string
  score: number
  source_file: string
  chunk_index: number
  page: number | null
  doc_id: string
}

export interface DocListParams {
  page?: number
  pageSize?: number
}

/** snake_case → camelCase */
function mapDoc(raw: RawDoc): DocItem {
  return {
    id: raw.id,
    fileName: raw.file_name,
    fileType: raw.file_type,
    fileSize: raw.file_size,
    chunkCount: raw.chunk_count,
    chunkStrategy: raw.chunk_strategy as ChunkStrategy,
    visibility: raw.visibility as DocVisibility,
    allowedRoles: (raw.allowed_roles ?? []) as RoleCode[],
    isOwner: raw.is_owner,
    createdAt: raw.created_at,
  }
}

/** 分页查询当前租户文档（按可见性过滤） */
export async function fetchDocuments(params: DocListParams = {}): Promise<PageResult<DocItem>> {
  const { data } = await request.get<RawPageResult>('/documents', {
    params: { page: params.page ?? 1, page_size: params.pageSize ?? 10 },
  })
  return {
    items: data.items.map(mapDoc),
    total: data.total,
    page: data.page,
    pageSize: data.page_size,
    totalPages: data.total_pages,
  }
}

/**
 * 上传文档（解析 → 切分 → 向量化入库）
 *
 * 使用 FormData 提交；Content-Type 由 axios 自动设置为带 boundary 的 multipart。
 */
export async function uploadDocument(
  file: File,
  params: DocUploadParams,
  onProgress?: (percent: number) => void,
): Promise<DocUploadResult> {
  const form = new FormData()
  form.append('file', file)
  form.append('strategy', params.strategy)
  form.append('visibility', params.visibility)
  if (params.visibility === 'roles' && params.allowedRoles?.length) {
    form.append('allowed_roles', params.allowedRoles.join(','))
  }

  const { data } = await request.post<RawUploadResult>('/documents', form, {
    timeout: 120000, // 解析 + 向量化耗时较长
    onUploadProgress: (e) => {
      if (onProgress && e.total) {
        onProgress(Math.round((e.loaded / e.total) * 100))
      }
    },
  })

  return {
    id: data.id,
    fileName: data.file_name,
    fileType: data.file_type,
    charCount: data.char_count,
    pageCount: data.page_count,
    chunkCount: data.chunk_count,
    chunkStrategy: data.chunk_strategy as ChunkStrategy,
  }
}

/** 删除文档（记录 + 向量 + 原文件；仅上传者本人或 admin） */
export async function deleteDocument(docId: string): Promise<void> {
  await request.delete(`/documents/${docId}`)
}

/** 语义检索文本块 */
export async function searchChunks(
  query: string,
  topK = 5,
  docId?: string,
): Promise<SearchChunk[]> {
  const { data } = await request.get<{ chunks: RawSearchChunk[] }>('/documents/search', {
    params: { q: query, top_k: topK, doc_id: docId },
  })
  return data.chunks.map((c) => ({
    text: c.text,
    score: c.score,
    sourceFile: c.source_file,
    chunkIndex: c.chunk_index,
    page: c.page,
    docId: c.doc_id,
  }))
}
