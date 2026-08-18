import request from '@/utils/request'
import type { Tenant, TenantFormData, PageResult } from '@/types'

/**
 * 租户管理 API
 * 对接后端 /api/tenants/*
 */

interface RawTenant {
  id: string
  name: string
  plan: Tenant['plan']
  status: Tenant['status']
  created_at: string
  updated_at: string
}

interface RawPageResult {
  items: RawTenant[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

interface TenantListParams {
  page?: number
  pageSize?: number
  name?: string
  plan?: string
  status?: string
}

/** 将后端 snake_case 字段映射为前端 camelCase */
function mapTenant(raw: RawTenant): Tenant {
  return {
    id: raw.id,
    name: raw.name,
    plan: raw.plan,
    status: raw.status,
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
  }
}

/** 分页查询租户列表 */
export async function fetchTenants(params: TenantListParams): Promise<PageResult<Tenant>> {
  const { data } = await request.get<RawPageResult>('/tenants', {
    params: {
      page: params.page,
      page_size: params.pageSize,
      name: params.name,
      plan: params.plan,
      status: params.status,
    },
  })
  return {
    items: data.items.map(mapTenant),
    total: data.total,
    page: data.page,
    pageSize: data.page_size,
    totalPages: data.total_pages,
  }
}

/** 创建租户 */
export async function createTenant(form: TenantFormData): Promise<Tenant> {
  const { data } = await request.post<RawTenant>('/tenants', form)
  return mapTenant(data)
}

/** 更新租户 */
export async function updateTenant(id: string, form: Partial<TenantFormData>): Promise<Tenant> {
  const { data } = await request.put<RawTenant>(`/tenants/${id}`, form)
  return mapTenant(data)
}

/** 删除租户 */
export async function deleteTenant(id: string): Promise<void> {
  await request.delete(`/tenants/${id}`)
}