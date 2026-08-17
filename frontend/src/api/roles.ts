import request from '@/utils/request'
import type { RoleOption } from '@/types'

/**
 * 角色 API
 * 对接后端 /api/roles
 */

interface RawRole {
  code: string
  name: string
}

/** 查询可分配角色列表（manager / auditor / employee） */
export async function fetchRoles(): Promise<RoleOption[]> {
  const { data } = await request.get<RawRole[]>('/roles')
  return data.map((r) => ({ code: r.code as RoleOption['code'], name: r.name }))
}