import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { UserRole } from '@/types'
import * as authApi from '@/api/auth'

/**
 * 认证授权 Store
 * 管理登录状态、Token、用户信息、租户上下文
 *
 * 类比：Spring SecurityContext + 自定义 Session 管理
 * - state.token ≈ JWT Token（存 localStorage 持久化）
 * - state.role ≈ 用户角色（前端按钮权限判断依据）
 * - isLoggedIn ≈ SecurityContext 是否有有效认证
 * - tenantContext ≈ 当前租户隔离上下文
 */
export const useAuthStore = defineStore('auth', () => {
  // ---------- 状态 ----------
  const token = ref<string>(localStorage.getItem('token') || '')
  const userId = ref<string>(localStorage.getItem('userId') || '')
  const username = ref<string>(localStorage.getItem('username') || '')
  const email = ref<string>(localStorage.getItem('email') || '')
  const role = ref<UserRole>((localStorage.getItem('role') as UserRole) || 'viewer')
  const tenantId = ref<string>(localStorage.getItem('tenantId') || '')
  const tenantName = ref<string>(localStorage.getItem('tenantName') || '')

  // ---------- 计算属性 (Getters) ----------
  const isLoggedIn = computed(() => !!token.value)

  /** 是否为管理员（控制前端按钮显隐） */
  const isAdmin = computed(() => role.value === 'admin')

  // ---------- 方法 (Actions) ----------
  /**
   * 登录
   * 调用后端 /api/auth/login 获取 token，再拉取用户信息
   */
  async function login(usernameInput: string, password: string): Promise<void> {
    const accessToken = await authApi.login(usernameInput, password)

    // 先写入 token（后续 /auth/me 请求需要）
    token.value = accessToken
    localStorage.setItem('token', accessToken)

    // 拉取当前用户信息
    const userInfo = await authApi.getMe()
    userId.value = userInfo.id
    username.value = userInfo.username
    email.value = userInfo.email
    role.value = userInfo.role
    tenantId.value = userInfo.tenantId
    tenantName.value = userInfo.tenantName

    localStorage.setItem('userId', userInfo.id)
    localStorage.setItem('username', userInfo.username)
    localStorage.setItem('email', userInfo.email)
    localStorage.setItem('role', userInfo.role)
    localStorage.setItem('tenantId', userInfo.tenantId)
    localStorage.setItem('tenantName', userInfo.tenantName)
  }

  /**
   * 刷新当前用户信息
   * 用于页面刷新后从 localStorage 恢复会话（token 仍有效时）
   */
  async function refreshUserInfo(): Promise<void> {
    if (!token.value) return
    try {
      const userInfo = await authApi.getMe()
      userId.value = userInfo.id
      username.value = userInfo.username
      email.value = userInfo.email
      role.value = userInfo.role
      tenantId.value = userInfo.tenantId
      tenantName.value = userInfo.tenantName

      localStorage.setItem('userId', userInfo.id)
      localStorage.setItem('username', userInfo.username)
      localStorage.setItem('email', userInfo.email)
      localStorage.setItem('role', userInfo.role)
      localStorage.setItem('tenantId', userInfo.tenantId)
      localStorage.setItem('tenantName', userInfo.tenantName)
    } catch {
      // token 失效由拦截器统一处理登出
    }
  }

  /**
   * 登出
   * 通知服务端后清除本地认证状态
   */
  async function logout(): Promise<void> {
    if (token.value) {
      await authApi.logout()
    }
    clearAuthState()
  }

  /** 仅清除本地认证状态（401 拦截器等内部使用，不发请求） */
  function clearAuthState(): void {
    token.value = ''
    userId.value = ''
    username.value = ''
    email.value = ''
    role.value = 'viewer'
    tenantId.value = ''
    tenantName.value = ''
    localStorage.removeItem('token')
    localStorage.removeItem('userId')
    localStorage.removeItem('username')
    localStorage.removeItem('email')
    localStorage.removeItem('role')
    localStorage.removeItem('tenantId')
    localStorage.removeItem('tenantName')
  }

  return {
    // 状态
    token,
    userId,
    username,
    email,
    role,
    tenantId,
    tenantName,
    // 计算属性
    isLoggedIn,
    isAdmin,
    // 方法
    login,
    refreshUserInfo,
    logout,
    clearAuthState,
  }
})