import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { User, UserFormData, UserFilter, Pagination } from '@/types'
import { mockUsers, getTenantNames } from '@/mock/users'

export const useUserStore = defineStore('user', () => {
  // ---------- 状态 ----------
  const users = ref<User[]>(mockUsers)
  const filter = ref<UserFilter>({
    username: '',
    role: '',
    tenantName: '',
  })
  const pagination = ref<Pagination>({
    page: 1,
    pageSize: 10,
    total: mockUsers.length,
  })

  // ---------- 计算属性 ----------
  /** 根据筛选条件过滤后的用户列表 */
  const filteredUsers = computed<User[]>(() => {
    let result = users.value

    if (filter.value.username) {
      const keyword = filter.value.username.toLowerCase()
      result = result.filter((u) =>
        u.username.toLowerCase().includes(keyword),
      )
    }

    if (filter.value.role) {
      result = result.filter((u) => u.role === filter.value.role)
    }

    if (filter.value.tenantName) {
      result = result.filter((u) => u.tenantName === filter.value.tenantName)
    }

    return result
  })

  /** 当前页的用户数据 */
  const pagedUsers = computed<User[]>(() => {
    const start = (pagination.value.page - 1) * pagination.value.pageSize
    const end = start + pagination.value.pageSize
    return filteredUsers.value.slice(start, end)
  })

  /** 筛选条件变化时重置分页 */
  function updatePaginationTotal(): void {
    pagination.value.total = filteredUsers.value.length
    // 如果当前页超出范围，回到第一页
    const maxPage = Math.max(
      1,
      Math.ceil(pagination.value.total / pagination.value.pageSize),
    )
    if (pagination.value.page > maxPage) {
      pagination.value.page = 1
    }
  }

  // ---------- 方法 ----------
  /** 更新筛选条件 */
  function setFilter(partial: Partial<UserFilter>): void {
    filter.value = { ...filter.value, ...partial }
    pagination.value.page = 1
    updatePaginationTotal()
  }

  /** 重置筛选条件 */
  function resetFilter(): void {
    filter.value = { username: '', role: '', tenantName: '' }
    pagination.value.page = 1
    updatePaginationTotal()
  }

  /** 设置当前页 */
  function setPage(page: number): void {
    pagination.value.page = page
  }

  /** 设置每页条数 */
  function setPageSize(size: number): void {
    pagination.value.pageSize = size
    pagination.value.page = 1
    updatePaginationTotal()
  }

  /** 新增用户 */
  function addUser(formData: UserFormData): void {
    const newUser: User = {
      id: String(Date.now()),
      ...formData,
      createdAt: new Date().toISOString().replace('T', ' ').slice(0, 19),
    }
    users.value.unshift(newUser)
    updatePaginationTotal()
  }

  /** 编辑用户 */
  function updateUser(id: string, formData: UserFormData): void {
    const index = users.value.findIndex((u) => u.id === id)
    if (index !== -1) {
      users.value[index] = { ...users.value[index], ...formData }
    }
  }

  /** 删除用户 */
  function deleteUser(id: string): void {
    users.value = users.value.filter((u) => u.id !== id)
    updatePaginationTotal()
  }

  return {
    // 状态
    users,
    filter,
    pagination,
    // 计算属性
    filteredUsers,
    pagedUsers,
    // 方法
    setFilter,
    resetFilter,
    setPage,
    setPageSize,
    addUser,
    updateUser,
    deleteUser,
    updatePaginationTotal,
  }
})

/** 获取租户列表 */
export function useTenantNames(): string[] {
  return getTenantNames()
}