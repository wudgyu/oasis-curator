import request from '@/utils/request'
import type { User, UserFormData, PageResult } from '@/types'

/**
 * 用户管理 API
 * 对接后端 /api/users/*
 *
 * 上下文租户通过 X-Tenant-Id 请求头传递（由 Axios 拦截器自动注入），
 * 后端按当前用户角色的数据范围过滤（employee 本组织 / auditor·manager 子树 / admin 全租户）。
 */

interface RawOrg {
  id: string
  name: string
  path: string
  parent_id: string | null
  tenant_id: string
  created_at: string
  updated_at: string
}

interface RawUser {
  id: string
  username: string
  email: string
  org: RawOrg
  role_code: string
  status: string
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
  orgId?: string
  includeChildren?: boolean
}

/** 将后端 snake_case 字段映射为前端 camelCase */
function mapUser(raw: RawUser): User {
  return {
    id: raw.id,
    username: raw.username,
    email: raw.email,
    org: {
      id: raw.org.id,
      name: raw.org.name,
      path: raw.org.path,
      parentId: raw.org.parent_id,
      tenantId: raw.org.tenant_id,
      createdAt: raw.org.created_at,
      updatedAt: raw.org.updated_at,
    },
    roleCode: raw.role_code as User['roleCode'],
    status: raw.status as User['status'],
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
  }
}

/** 分页查询用户列表（后端自动按角色数据范围过滤） */
export async function fetchUsers(params: UserListParams): Promise<PageResult<User>> {
  // 前端 camelCase → 后端 snake_case 参数名映射
  const { data } = await request.get<RawPageResult>('/users', {
    params: {
      page: params.page,
      page_size: params.pageSize,
      username: params.username,
      role: params.role,
      status: params.status,
      org_id: params.orgId,
      include_children: params.includeChildren,
    },
  })
  return {
    items: data.items.map(mapUser),
    total: data.total,
    page: data.page,
    pageSize: data.page_size,
    totalPages: data.total_pages,
  }
}

/** 新增用户（指定组织 + 角色） */
export async function createUser(form: UserFormData): Promise<User> {
  const { data } = await request.post<RawUser>('/users', {
    username: form.username,
    email: form.email,
    password: form.password,
    org_id: form.orgId,
    role_code: form.roleCode,
    status: form.status,
  })
  return mapUser(data)
}

/** 编辑用户 */
export async function updateUser(id: string, form: Partial<UserFormData>): Promise<User> {
  const payload: Record<string, unknown> = {
    username: form.username,
    email: form.email,
    password: form.password,
    status: form.status,
    role_code: form.roleCode,
    org_id: form.orgId,
  }
  // 剔除 undefined 字段（部分更新）
  Object.keys(payload).forEach((k) => payload[k] === undefined && delete payload[k])
  const { data } = await request.put<RawUser>(`/users/${id}`, payload)
  return mapUser(data)
}

/** 删除用户 */
export async function deleteUser(id: string): Promise<void> {
  await request.delete(`/users/${id}`)
}