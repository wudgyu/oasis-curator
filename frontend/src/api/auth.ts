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
  role_code: string
  status: string
  tenant: { id: string; name: string } | null
  org: { id: string; name: string; path: string } | null
}

/** 将后端 snake_case 字段映射为前端 camelCase */
function mapUserInfo(raw: RawUserInfo): UserInfo {
  return {
    id: raw.id,
    username: raw.username,
    email: raw.email,
    roleCode: raw.role_code as UserInfo['roleCode'],
    status: raw.status as UserInfo['status'],
    tenant: raw.tenant,
    org: raw.org,
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

/** 获取当前用户信息（role_code + tenant + org） */
export async function getMe(): Promise<UserInfo> {
  const { data } = await request.get<RawUserInfo>('/auth/me')
  return mapUserInfo(data)
}