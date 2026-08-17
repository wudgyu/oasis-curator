import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { RoleCode, TenantBrief, OrgBrief } from '@/types'
import * as authApi from '@/api/auth'

/**
 * 认证授权 Store（RBAC 模型）
 * 管理登录状态、Token、用户信息、租户/组织上下文
 *
 * - roleCode: admin（平台管理员）/ manager / auditor / employee
 * - 普通用户唯一归属一个租户；admin 通过 currentTenantId 切换工作区
 * - 角色变更以后端为准（每次刷新 /auth/me 重新拉取）
 */
export const useAuthStore = defineStore('auth', () => {
  // ---------- 状态 ----------
  const token = ref<string>(localStorage.getItem('token') || '')
  const userId = ref<string>(localStorage.getItem('userId') || '')
  const username = ref<string>(localStorage.getItem('username') || '')
  const email = ref<string>(localStorage.getItem('email') || '')
  const roleCode = ref<RoleCode>((localStorage.getItem('roleCode') as RoleCode) || 'employee')
  const tenantId = ref<string>(localStorage.getItem('tenantId') || '')
  const tenantName = ref<string>(localStorage.getItem('tenantName') || '')
  const orgId = ref<string>(localStorage.getItem('orgId') || '')
  const orgName = ref<string>(localStorage.getItem('orgName') || '')
  const orgPath = ref<string>(localStorage.getItem('orgPath') || '')

  /** admin 当前工作区租户（普通用户恒等于自身租户） */
  const currentTenantId = ref<string>(
    localStorage.getItem('currentTenantId') || tenantId.value || '',
  )

  // ---------- 计算属性 (Getters) ----------
  const isLoggedIn = computed(() => !!token.value)

  /** 是否为平台管理员 */
  const isAdmin = computed(() => roleCode.value === 'admin')

  /** 是否有写权限（admin / manager） */
  const canWrite = computed(() => ['admin', 'manager'].includes(roleCode.value))

  /** 是否显示租户切换器（仅 admin） */
  const canSwitchTenant = computed(() => isAdmin.value)

  // ---------- 方法 (Actions) ----------
  /** 将 /auth/me 的用户信息写入状态与 localStorage */
  function applyUserInfo(userInfo: {
    id: string
    username: string
    email: string
    roleCode: RoleCode
    tenant: TenantBrief | null
    org: OrgBrief | null
  }): void {
    userId.value = userInfo.id
    username.value = userInfo.username
    email.value = userInfo.email
    roleCode.value = userInfo.roleCode
    tenantId.value = userInfo.tenant?.id ?? ''
    tenantName.value = userInfo.tenant?.name ?? ''
    orgId.value = userInfo.org?.id ?? ''
    orgName.value = userInfo.org?.name ?? ''
    orgPath.value = userInfo.org?.path ?? ''

    // 上下文租户：admin 保持已选工作区（无则默认首个可见租户 = 自身 tenant 为空的场景后续由租户列表回填）
    if (currentTenantId.value === '' || !localStorage.getItem('currentTenantId')) {
      currentTenantId.value = tenantId.value
      if (currentTenantId.value) {
        localStorage.setItem('currentTenantId', currentTenantId.value)
      }
    }

    localStorage.setItem('userId', userInfo.id)
    localStorage.setItem('username', userInfo.username)
    localStorage.setItem('email', userInfo.email)
    localStorage.setItem('roleCode', userInfo.roleCode)
    localStorage.setItem('tenantId', tenantId.value)
    localStorage.setItem('tenantName', tenantName.value)
    localStorage.setItem('orgId', orgId.value)
    localStorage.setItem('orgName', orgName.value)
    localStorage.setItem('orgPath', orgPath.value)
  }

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
    applyUserInfo(userInfo)
  }

  /**
   * 刷新当前用户信息
   * 用于页面刷新后从 localStorage 恢复会话（token 仍有效时）
   */
  async function refreshUserInfo(): Promise<void> {
    if (!token.value) return
    try {
      const userInfo = await authApi.getMe()
      applyUserInfo(userInfo)
    } catch {
      // token 失效由拦截器统一处理登出
    }
  }

  /**
   * 切换 admin 的当前工作区租户
   * 切换后依赖该上下文的页面（组织树、用户列表、首页统计）自动刷新
   */
  function switchTenant(tenantIdInput: string): void {
    currentTenantId.value = tenantIdInput
    localStorage.setItem('currentTenantId', tenantIdInput)
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
    roleCode.value = 'employee'
    tenantId.value = ''
    tenantName.value = ''
    orgId.value = ''
    orgName.value = ''
    orgPath.value = ''
    currentTenantId.value = ''
    localStorage.removeItem('token')
    localStorage.removeItem('userId')
    localStorage.removeItem('username')
    localStorage.removeItem('email')
    localStorage.removeItem('roleCode')
    localStorage.removeItem('tenantId')
    localStorage.removeItem('tenantName')
    localStorage.removeItem('orgId')
    localStorage.removeItem('orgName')
    localStorage.removeItem('orgPath')
    localStorage.removeItem('currentTenantId')
  }

  return {
    // 状态
    token,
    userId,
    username,
    email,
    roleCode,
    tenantId,
    tenantName,
    orgId,
    orgName,
    orgPath,
    currentTenantId,
    // 计算属性
    isLoggedIn,
    isAdmin,
    canWrite,
    canSwitchTenant,
    // 方法
    login,
    refreshUserInfo,
    switchTenant,
    logout,
    clearAuthState,
  }
})