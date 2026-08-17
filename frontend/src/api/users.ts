import request from '@/utils/request'
import type { User, UserFormData, PageResult } from '@/types'

/**
 * 用户管理 API
 * 对接后端 /api/users/*
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
  }
}

/** 分页查询用户列表（后端自动按当前租户隔离） */
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

/** 新增用户 */
export async function createUser(form: UserFormData): Promise<User> {
  const { data } = await request.post<RawUser>('/users', form)
  return mapUser(data)
}

/** 编辑用户 */
export async function updateUser(id: string, form: Partial<UserFormData>): Promise<User> {
  const { data } = await request.put<RawUser>(`/users/${id}`, form)
  return mapUser(data)
}

/** 删除用户 */
export async function deleteUser(id: string): Promise<void> {
  await request.delete(`/users/${id}`)
}