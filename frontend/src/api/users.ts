import request from '@/utils/request'
import type { User, UserFormData, PageResult } from '@/types'

/**
 * 用户管理 API
 * 对接后端 /api/users/*
 *
 * 上下文租户通过 X-Tenant-Id 请求头传递（由 Axios 拦截器自动注入），
 * 后端按该租户做数据隔离。
 */

interface RawUser {
  id: string
  username: string
  email: string
  tenant_id: string
  tenant_name: string
  role: User['role']
  status: User['status']
  created_at: string
  updated_at: string
  tenant_ids: string[]
}

interface RawPageResult {
  items: RawUser[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

interface UserListParams {
  page?: number
  pageSize?: number
  username?: string
  role?: string
  status?: string
}

/** 将后端 snake_case 字段映射为前端 camelCase */
function mapUser(raw: RawUser): User {
  return {
    id: raw.id,
    username: raw.username,
    email: raw.email,
    tenantId: raw.tenant_id,
    tenantName: raw.tenant_name,
    role: raw.role,
    status: raw.status,
    createdAt: raw.created_at,
    tenantIds: raw.tenant_ids ?? [],
  }
}

/** 分页查询用户列表（后端自动按上下文租户隔离） */
export async function fetchUsers(params: UserListParams): Promise<PageResult<User>> {
  const { data } = await request.get<RawPageResult>('/users', { params })
  return {
    items: data.items.map(mapUser),
    total: data.total,
    page: data.page,
    pageSize: data.page_size,
    totalPages: data.total_pages,
  }
}

/** 新增用户（归属上下文租户，tenant_ids 指定可访问的其它租户） */
export async function createUser(form: UserFormData): Promise<User> {
  const { data } = await request.post<RawUser>('/users', {
    username: form.username,
    email: form.email,
    password: form.password,
    role: form.role,
    status: form.status,
    tenant_ids: form.tenantIds ?? [],
  })
  return mapUser(data)
}

/** 编辑用户 */
export async function updateUser(id: string, form: Partial<UserFormData>): Promise<User> {
  const payload: Record<string, unknown> = { ...form }
  if ('tenantIds' in payload) {
    payload.tenant_ids = payload.tenantIds ?? []
    delete payload.tenantIds
  }
  const { data } = await request.put<RawUser>(`/users/${id}`, payload)
  return mapUser(data)
}

/** 删除用户 */
export async function deleteUser(id: string): Promise<void> {
  await request.delete(`/users/${id}`)
}