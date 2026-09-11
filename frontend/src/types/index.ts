/** RBAC 角色 code（admin 为平台内置，不可经业务 API 分配） */
export type RoleCode = 'admin' | 'manager' | 'auditor' | 'employee'

/** 可分配角色（排除平台 admin） */
export type AssignableRoleCode = 'manager' | 'auditor' | 'employee'

/** 用户状态 */
export type UserStatus = 'active' | 'disabled'

/** 节点权限 */
export type NodeAuth = 'manage' | 'view' | 'none'

/** 租户简要信息 */
export interface TenantBrief {
  id: string
  name: string
}

/** 组织简要信息 */
export interface OrgBrief {
  id: string
  name: string
  path: string
}

/** 组织树节点（嵌套结构，对接 /api/orgs/tree） */
export interface OrgTreeNode {
  id: string
  name: string
  path: string
  parentId: string | null
  userCount: number
  children: OrgTreeNode[]
}

/** 组织实体（对接 /api/orgs） */
export interface Org {
  id: string
  name: string
  path: string
  parentId: string | null
  tenantId: string
  createdAt: string
  updatedAt: string
}

/** 用户实体（对接后端 /api/users） */
export interface User {
  id: string
  username: string
  email: string
  org: Org
  roleCode: RoleCode
  status: UserStatus
  createdAt: string
  updatedAt: string
}

/** 用户表单数据（新增/编辑） */
export interface UserFormData {
  username: string
  email: string
  /** 新增时必填；编辑时留空表示不修改 */
  password: string
  orgId: string
  roleCode: AssignableRoleCode
  status: UserStatus
}

/** 用户筛选条件 */
export interface UserFilter {
  username: string
  role: RoleCode | ''
  status: UserStatus | ''
  orgId: string
}

/** 可选角色项（对接 /api/roles） */
export interface RoleOption {
  code: AssignableRoleCode
  name: string
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
  roleCode: RoleCode
  status: UserStatus
  /** 平台管理员为 null */
  tenant: TenantBrief | null
  /** 平台管理员为 null */
  org: OrgBrief | null
}

/** IAM 配置生成器 */
export interface IamTemplate {
  name: string
  description: string
  keywords: string[]
}

export interface IamGenerateResult {
  config: Record<string, unknown>
  template_matched: boolean
  template_name: string | null
  retries: number
  conflicts: string[]
}

/** IAM 角色保存 */
export interface IamSaveRoleResult {
  id: string
  code: string
  name: string
  overwritten: boolean
}

/** IAM 角色列表项（含内置 + 自定义） */
export interface IamRoleItem {
  id: string
  code: string
  name: string
  description: string | null
  builtin: boolean
  tenant_id: string | null
  permissions: Array<{ resource: string; actions: string[] }> | null
  data_scope: Record<string, unknown> | null
  created_at: string
}
// ==================== 文档管理（RAG） ====================

/** 文档可见性：tenant 租户公开 / private 仅上传者 / roles 指定角色 */
export type DocVisibility = 'tenant' | 'private' | 'roles'

/** 切分策略 */
export type ChunkStrategy = 'paragraphs' | 'chars'

/** 文档列表项（对接 /api/documents） */
export interface DocItem {
  id: string
  fileName: string
  fileType: string
  fileSize: number
  chunkCount: number
  chunkStrategy: ChunkStrategy
  visibility: DocVisibility
  allowedRoles: RoleCode[]
  isOwner: boolean
  createdAt: string
}

/** 文档上传参数 */
export interface DocUploadParams {
  strategy: ChunkStrategy
  visibility: DocVisibility
  allowedRoles?: RoleCode[]
}

/** 文档上传结果 */
export interface DocUploadResult {
  id: string
  fileName: string
  fileType: string
  charCount: number
  pageCount: number
  chunkCount: number
  chunkStrategy: ChunkStrategy
}

/** 语义检索命中块（对接 /api/documents/search） */
export interface SearchChunk {
  text: string
  score: number
  sourceFile: string
  chunkIndex: number
  page: number | null
  docId: string
}
