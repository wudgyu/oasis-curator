import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

/**
 * 认证授权 Store
 * 管理登录状态、Token、用户信息、租户上下文
 *
 * 类比：Spring SecurityContext + 自定义 Session 管理
 * - state.token ≈ JWT Token（存 localStorage 持久化）
 * - state.username ≈ SecurityContextHolder.getContext().getAuthentication().getName()
 * - isLoggedIn ≈ SecurityContext 是否有有效认证
 * - tenantContext ≈ 当前租户隔离上下文
 */
export const useAuthStore = defineStore('auth', () => {
  // ---------- 状态 ----------
  const token = ref<string>(localStorage.getItem('token') || '')
  const username = ref<string>(localStorage.getItem('username') || '')
  const tenantId = ref<string>(localStorage.getItem('tenantId') || '')
  const tenantName = ref<string>(localStorage.getItem('tenantName') || '')

  // ---------- 计算属性 (Getters) ----------
  const isLoggedIn = computed(() => !!token.value)

  // ---------- 方法 (Actions) ----------
  /**
   * 登录
   * 存储 token 和用户信息到 localStorage 持久化
   */
  function login(accessToken: string, user: string, tenant?: { id: string; name: string }): void {
    token.value = accessToken
    username.value = user
    localStorage.setItem('token', accessToken)
    localStorage.setItem('username', user)

    if (tenant) {
      tenantId.value = tenant.id
      tenantName.value = tenant.name
      localStorage.setItem('tenantId', tenant.id)
      localStorage.setItem('tenantName', tenant.name)
    }
  }

  /**
   * 登出
   * 清除所有认证状态
   */
  function logout(): void {
    token.value = ''
    username.value = ''
    tenantId.value = ''
    tenantName.value = ''
    localStorage.removeItem('token')
    localStorage.removeItem('username')
    localStorage.removeItem('tenantId')
    localStorage.removeItem('tenantName')
  }

  return {
    // 状态
    token,
    username,
    tenantId,
    tenantName,
    // 计算属性
    isLoggedIn,
    // 方法
    login,
    logout,
  }
})