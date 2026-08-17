import request from '@/utils/request'
import type { UserInfo } from '@/types'

/**
 * 认证 API
 * 对接后端 /api/auth/*
 */

interface LoginResponse {
  access_token: string
  token_type: string
}

interface RawUserInfo {
  id: string
  username: string
  email: string
  tenant_id: string
  tenant_name: string
  role: UserInfo['role']
  status: UserInfo['status']
  tenants: { id: string; name: string }[]
}

/** 将后端 snake_case 字段映射为前端 camelCase */
function mapUserInfo(raw: RawUserInfo): UserInfo {
  return {
    id: raw.id,
    username: raw.username,
    email: raw.email,
    tenantId: raw.tenant_id,
    tenantName: raw.tenant_name,
    role: raw.role,
    status: raw.status,
    accessibleTenants: raw.tenants.map((t) => ({ id: t.id, name: t.name })),
  }
}

/** 登录，返回 access_token */
export async function login(username: string, password: string): Promise<string> {
  const { data } = await request.post<LoginResponse>('/auth/login', { username, password })
  return data.access_token
}

/** 登出（尽力通知服务端，失败不阻塞） */
export async function logout(): Promise<void> {
  try {
    await request.post('/auth/logout')
  } catch {
    // 登出失败不影响本地清除登录态
  }
}

/** 获取当前用户信息（含可访问租户列表） */
export async function getMe(): Promise<UserInfo> {
  const { data } = await request.get<RawUserInfo>('/auth/me')
  return mapUserInfo(data)
}