/** 用户角色枚举 */
export type UserRole = 'admin' | 'editor' | 'viewer'

/** 用户状态 */
export type UserStatus = 'active' | 'disabled'

/** 用户实体 */
export interface User {
  id: string
  username: string
  email: string
  tenantName: string
  role: UserRole
  status: UserStatus
  createdAt: string
}

/** 用户表单数据（新增/编辑） */
export interface UserFormData {
  username: string
  email: string
  tenantName: string
  role: UserRole
  status: UserStatus
}

/** 搜索筛选条件 */
export interface UserFilter {
  username: string
  role: UserRole | ''
  tenantName: string
}

/** 分页参数 */
export interface Pagination {
  page: number
  pageSize: number
  total: number
}

/** 租户套餐 */
export type TenantPlan = 'basic' | 'pro' | 'enterprise'

/** 租户状态 */
export type TenantStatus = 'active' | 'disabled'

/** 租户实体 */
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