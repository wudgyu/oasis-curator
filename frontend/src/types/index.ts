/** 用户角色枚举 */
export type UserRole = 'admin' | 'editor' | 'viewer'

/** 用户状态 */
export type UserStatus = 'active' | 'disabled'

/** 用户实体（对接后端 /api/users） */
export interface User {
  id: string
  username: string
  email: string
  tenantId: string
  tenantName: string
  role: UserRole
  status: UserStatus
  createdAt: string
  /** 可访问的其它租户 ID（不含主租户） */
  tenantIds: string[]
}

/** 用户表单数据（新增/编辑） */
export interface UserFormData {
  username: string
  email: string
  /** 新增时必填；编辑时留空表示不修改 */
  password: string
  role: UserRole
  status: UserStatus
  /** 可访问的其它租户 ID（不含主租户） */
  tenantIds?: string[]
}

/** 搜索筛选条件 */
export interface UserFilter {
  username: string
  role: UserRole | ''
  status: UserStatus | ''
}

/** 分页参数 */
export interface Pagination {
  page: number
  pageSize: number
  total: number
}

/** 服务端分页响应通用结构 */
export interface PageResult<T> {
  items: T[]
  total: number
  page: number
  pageSize: number
  totalPages: number
}

/** 租户套餐 */
export type TenantPlan = 'basic' | 'pro' | 'enterprise'

/** 租户状态 */
export type TenantStatus = 'active' | 'disabled'

/** 租户实体（对接后端 /api/tenants） */
export interface Tenant {
  id: string
  name: string
  plan: TenantPlan
  status: TenantStatus
  createdAt: string
  updatedAt: string
}

/** 租户表单数据（新增/编辑） */
export interface TenantFormData {
  name: string
  plan: TenantPlan
  status: TenantStatus
}

/** 租户筛选条件 */
export interface TenantFilter {
  name: string
  plan: TenantPlan | ''
  status: TenantStatus | ''
}

/** 当前登录用户信息（/api/auth/me） */
export interface UserInfo {
  id: string
  username: string
  email: string
  tenantId: string
  tenantName: string
  role: UserRole
  status: UserStatus
  /** 可访问的租户列表（主租户在前），用于切换当前租户 */
  accessibleTenants: TenantBrief[]
}

/** 租户简要信息 */
export interface TenantBrief {
  id: string
  name: string
}