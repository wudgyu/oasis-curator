import request from '@/utils/request'
import type { Org, OrgTreeNode } from '@/types'

/**
 * 组织管理 API
 * 对接后端 /api/orgs/*
 *
 * 上下文租户通过 X-Tenant-Id 请求头传递（由 Axios 拦截器自动注入，
 * 平台 admin 必填，普通用户固定为自身租户）。
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

interface RawTreeNode {
  id: string
  name: string
  path: string
  parent_id: string | null
  user_count: number
  children: RawTreeNode[]
}

function mapOrg(raw: RawOrg): Org {
  return {
    id: raw.id,
    name: raw.name,
    path: raw.path,
    parentId: raw.parent_id,
    tenantId: raw.tenant_id,
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
  }
}

function mapTreeNode(raw: RawTreeNode): OrgTreeNode {
  return {
    id: raw.id,
    name: raw.name,
    path: raw.path,
    parentId: raw.parent_id,
    userCount: raw.user_count,
    children: raw.children.map(mapTreeNode),
  }
}

/** 查询上下文租户的完整组织树 */
export async function fetchOrgTree(): Promise<OrgTreeNode[]> {
  const { data } = await request.get<RawTreeNode[]>('/orgs/tree')
  return data.map(mapTreeNode)
}

/** 在父组织下创建子组织 */
export async function createOrg(name: string, parentId: string): Promise<Org> {
  const { data } = await request.post<RawOrg>('/orgs', { name, parent_id: parentId })
  return mapOrg(data)
}

/** 重命名组织 */
export async function renameOrg(id: string, name: string): Promise<Org> {
  const { data } = await request.put<RawOrg>(`/orgs/${id}`, { name })
  return mapOrg(data)
}

/** 移动组织到新父组织 */
export async function moveOrg(id: string, newParentId: string): Promise<Org> {
  const { data } = await request.post<RawOrg>(`/orgs/${id}/move`, { new_parent_id: newParentId })
  return mapOrg(data)
}

/** 删除组织（仅空组织） */
export async function deleteOrg(id: string): Promise<void> {
  await request.delete(`/orgs/${id}`)
}