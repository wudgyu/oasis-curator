import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { Tenant, TenantFormData, TenantFilter } from '@/types'
import { fetchTenants, createTenant, updateTenant, deleteTenant } from '@/api/tenants'

/**
 * 租户管理 Store（服务端分页 + 筛选）
 *
 * 数据由 FastAPI 后端提供，筛选和分页在服务端完成。
 * 仅 admin 角色可访问（后端校验 + 前端路由守卫双重保障）。
 */
export const useTenantStore = defineStore('tenant', () => {
  // ---------- 状态 ----------
  /** 当前页租户数据 */
  const tenants = ref<Tenant[]>([])
  /** 加载状态 */
  const loading = ref(false)
  /** 服务端返回的总条数 */
  const total = ref(0)
  const filter = ref<TenantFilter>({
    name: '',
    plan: '',
    status: '',
  })
  const page = ref(1)
  const pageSize = ref(10)

  // ---------- 方法 ----------
  /** 从服务端拉取当前筛选条件下的租户列表 */
  async function fetchTenantList(): Promise<void> {
    loading.value = true
    try {
      const result = await fetchTenants({
        page: page.value,
        pageSize: pageSize.value,
        name: filter.value.name || undefined,
        plan: filter.value.plan || undefined,
        status: filter.value.status || undefined,
      })
      tenants.value = result.items
      total.value = result.total
      // 删除最后一条后可能超出页数范围，回退到最后一页
      if (result.items.length === 0 && page.value > 1 && result.totalPages > 0) {
        page.value = result.totalPages
        await fetchTenantList()
      }
    } finally {
      loading.value = false
    }
  }

  /** 更新筛选条件并重新查询 */
  function setFilter(partial: Partial<TenantFilter>): void {
    filter.value = { ...filter.value, ...partial }
    page.value = 1
    fetchTenantList()
  }

  /** 重置筛选条件并重新查询 */
  function resetFilter(): void {
    filter.value = { name: '', plan: '', status: '' }
    page.value = 1
    fetchTenantList()
  }

  /** 切换页码 */
  function setPage(newPage: number): void {
    page.value = newPage
    fetchTenantList()
  }

  /** 切换每页条数 */
  function setPageSize(size: number): void {
    pageSize.value = size
    page.value = 1
    fetchTenantList()
  }

  /** 新增租户（成功后刷新列表） */
  async function addTenant(formData: TenantFormData): Promise<void> {
    await createTenant(formData)
    await fetchTenantList()
  }

  /** 编辑租户（成功后刷新列表） */
  async function editTenant(id: string, formData: TenantFormData): Promise<void> {
    await updateTenant(id, formData)
    await fetchTenantList()
  }

  /** 删除租户（成功后刷新列表） */
  async function removeTenant(id: string): Promise<void> {
    await deleteTenant(id)
    await fetchTenantList()
  }

  return {
    // 状态
    tenants,
    loading,
    total,
    filter,
    page,
    pageSize,
    // 方法
    fetchTenantList,
    setFilter,
    resetFilter,
    setPage,
    setPageSize,
    addTenant,
    editTenant,
    removeTenant,
  }
})