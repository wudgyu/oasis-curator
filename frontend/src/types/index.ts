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