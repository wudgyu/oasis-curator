import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { User, UserFormData, UserFilter } from '@/types'
import { fetchUsers, createUser, updateUser, deleteUser } from '@/api/users'

/**
 * 用户管理 Store（服务端分页 + 筛选 + 角色数据范围）
 *
 * 数据由 FastAPI 后端提供，后端自动按当前用户角色的数据范围过滤：
 * employee 仅本组织 / auditor·manager 子树 / admin 上下文租户全量。
 */
export const useUserStore = defineStore('user', () => {
  // ---------- 状态 ----------
  /** 当前页用户数据 */
  const users = ref<User[]>([])
  /** 加载状态 */
  const loading = ref(false)
  /** 服务端返回的总条数 */
  const total = ref(0)
  const filter = ref<UserFilter>({
    username: '',
    role: '',
    status: '',
    orgId: '',
  })
  const page = ref(1)
  const pageSize = ref(10)

  // ---------- 方法 ----------
  /** 从服务端拉取当前筛选条件下的用户列表 */
  async function fetchUserList(): Promise<void> {
    loading.value = true
    try {
      const result = await fetchUsers({
        page: page.value,
        pageSize: pageSize.value,
        username: filter.value.username || undefined,
        role: filter.value.role || undefined,
        status: filter.value.status || undefined,
        orgId: filter.value.orgId || undefined,
        includeChildren: !!filter.value.orgId, // 按组织筛选默认含子树
      })
      users.value = result.items
      total.value = result.total
      // 删除最后一条后可能超出页数范围，回退到最后一页
      if (result.items.length === 0 && page.value > 1 && result.totalPages > 0) {
        page.value = result.totalPages
        await fetchUserList()
      }
    } finally {
      loading.value = false
    }
  }

  /** 更新筛选条件并重新查询 */
  function setFilter(partial: Partial<UserFilter>): void {
    filter.value = { ...filter.value, ...partial }
    page.value = 1
    fetchUserList()
  }

  /** 重置筛选条件并重新查询 */
  function resetFilter(): void {
    filter.value = { username: '', role: '', status: '', orgId: '' }
    page.value = 1
    fetchUserList()
  }

  /** 切换页码 */
  function setPage(newPage: number): void {
    page.value = newPage
    fetchUserList()
  }

  /** 切换每页条数 */
  function setPageSize(size: number): void {
    pageSize.value = size
    page.value = 1
    fetchUserList()
  }

  /** 新增用户（成功后刷新列表） */
  async function addUser(formData: UserFormData): Promise<void> {
    await createUser(formData)
    await fetchUserList()
  }

  /** 编辑用户（成功后刷新列表） */
  async function editUser(id: string, formData: Partial<UserFormData>): Promise<void> {
    await updateUser(id, formData)
    await fetchUserList()
  }

  /** 删除用户（成功后刷新列表） */
  async function removeUser(id: string): Promise<void> {
    await deleteUser(id)
    await fetchUserList()
  }

  return {
    // 状态
    users,
    loading,
    total,
    filter,
    page,
    pageSize,
    // 方法
    fetchUserList,
    setFilter,
    resetFilter,
    setPage,
    setPageSize,
    addUser,
    editUser,
    removeUser,
  }
})