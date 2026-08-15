<script setup lang="ts">
import type { Tenant, TenantPlan, TenantStatus } from '@/types'

/**
 * 租户表格组件
 */

// ---------- Props ----------
defineProps<{
  /** 租户数据列表 */
  tenants: Tenant[]
  /** 是否加载中 */
  loading?: boolean
}>()

// ---------- Emits ----------
const emit = defineEmits<{
  /** 编辑租户 */
  (e: 'edit', tenant: Tenant): void
  /** 删除租户 */
  (e: 'delete', tenant: Tenant): void
}>()

// ---------- 辅助函数 ----------
function getPlanTagType(plan: TenantPlan): 'danger' | 'warning' | 'success' {
  const map: Record<TenantPlan, 'danger' | 'warning' | 'success'> = {
    enterprise: 'danger',
    pro: 'warning',
    basic: 'success',
  }
  return map[plan]
}

function getPlanLabel(plan: TenantPlan): string {
  const map: Record<TenantPlan, string> = {
    enterprise: '企业版',
    pro: '专业版',
    basic: '基础版',
  }
  return map[plan]
}

function getStatusLabel(status: TenantStatus): string {
  return status === 'active' ? '启用' : '禁用'
}
</script>

<template>
  <el-table
    :data="tenants"
    border
    stripe
    style="width: 100%"
    empty-text="暂无数据"
    v-loading="loading"
  >
    <el-table-column prop="name" label="租户名称" min-width="160" />
    <el-table-column label="套餐" width="100">
      <template #default="{ row }">
        <el-tag :type="getPlanTagType(row.plan)" size="small">
          {{ getPlanLabel(row.plan) }}
        </el-tag>
      </template>
    </el-table-column>
    <el-table-column label="状态" width="80">
      <template #default="{ row }">
        <el-tag
          :type="row.status === 'active' ? 'success' : 'info'"
          size="small"
        >
          {{ getStatusLabel(row.status) }}
        </el-tag>
      </template>
    </el-table-column>
    <el-table-column prop="createdAt" label="创建时间" width="180" />
    <el-table-column prop="updatedAt" label="更新时间" width="180" />
    <el-table-column label="操作" width="160" fixed="right">
      <template #default="{ row }">
        <el-button type="primary" link size="small" @click="emit('edit', (row as Tenant))">
          编辑
        </el-button>
        <el-button type="danger" link size="small" @click="emit('delete', (row as Tenant))">
          删除
        </el-button>
      </template>
    </el-table-column>
  </el-table>
</template>