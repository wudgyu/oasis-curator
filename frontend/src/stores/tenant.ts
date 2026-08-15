import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { Tenant, TenantFormData, TenantFilter, Pagination } from '@/types'
import { mockTenants } from '@/mock/tenants'

export const useTenantStore = defineStore('tenant', () => {
  // ---------- 状态 ----------
  const tenants = ref<Tenant[]>(mockTenants)
  const filter = ref<TenantFilter>({
    name: '',
    plan: '',
    status: '',
  })
  const pagination = ref<Pagination>({
    page: 1,
    pageSize: 10,
    total: mockTenants.length,
  })

  // ---------- 计算属性 ----------
  /** 根据筛选条件过滤后的租户列表 */
  const filteredTenants = computed<Tenant[]>(() => {
    let result = tenants.value

    if (filter.value.name) {
      const keyword = filter.value.name.toLowerCase()
      result = result.filter((t) => t.name.toLowerCase().includes(keyword))
    }

    if (filter.value.plan) {
      result = result.filter((t) => t.plan === filter.value.plan)
    }

    if (filter.value.status) {
      result = result.filter((t) => t.status === filter.value.status)
    }

    return result
  })

  /** 当前页的租户数据 */
  const pagedTenants = computed<Tenant[]>(() => {
    const start = (pagination.value.page - 1) * pagination.value.pageSize
    const end = start + pagination.value.pageSize
    return filteredTenants.value.slice(start, end)
  })

  /** 筛选条件变化时重置分页 */
  function updatePaginationTotal(): void {
    pagination.value.total = filteredTenants.value.length
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
  function setFilter(partial: Partial<TenantFilter>): void {
    filter.value = { ...filter.value, ...partial }
    pagination.value.page = 1
    updatePaginationTotal()
  }

  /** 重置筛选条件 */
  function resetFilter(): void {
    filter.value = { name: '', plan: '', status: '' }
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

  /** 新增租户 */
  function addTenant(formData: TenantFormData): void {
    const now = new Date().toISOString().replace('T', ' ').slice(0, 19)
    const newTenant: Tenant = {
      id: `tenant-${Date.now()}`,
      ...formData,
      createdAt: now,
      updatedAt: now,
    }
    tenants.value.unshift(newTenant)
    updatePaginationTotal()
  }

  /** 编辑租户 */
  function updateTenant(id: string, formData: TenantFormData): void {
    const index = tenants.value.findIndex((t) => t.id === id)
    if (index !== -1) {
      const now = new Date().toISOString().replace('T', ' ').slice(0, 19)
      tenants.value[index] = {
        ...tenants.value[index],
        ...formData,
        updatedAt: now,
      }
    }
  }

  /** 删除租户 */
  function deleteTenant(id: string): void {
    tenants.value = tenants.value.filter((t) => t.id !== id)
    updatePaginationTotal()
  }

  return {
    // 状态
    tenants,
    filter,
    pagination,
    // 计算属性
    filteredTenants,
    pagedTenants,
    // 方法
    setFilter,
    resetFilter,
    setPage,
    setPageSize,
    addTenant,
    updateTenant,
    deleteTenant,
    updatePaginationTotal,
  }
})