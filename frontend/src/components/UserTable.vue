<script setup lang="ts">
import type { User, UserRole, UserStatus } from '@/types'

/**
 * 用户表格组件
 * 展示 defineProps<T>() 和 defineEmits<T>() 的 TypeScript 泛型用法
 */

// ---------- Props ----------
defineProps<{
  /** 用户数据列表 */
  users: User[]
  /** 是否加载中 */
  loading?: boolean
}>()

// ---------- Emits ----------
const emit = defineEmits<{
  /** 编辑用户 */
  (e: 'edit', user: User): void
  /** 删除用户 */
  (e: 'delete', user: User): void
}>()

// ---------- 辅助函数 ----------
function getRoleTagType(role: UserRole): 'danger' | 'warning' | 'info' {
  const map: Record<UserRole, 'danger' | 'warning' | 'info'> = {
    admin: 'danger',
    editor: 'warning',
    viewer: 'info',
  }
  return map[role]
}

function getRoleLabel(role: UserRole): string {
  const map: Record<UserRole, string> = {
    admin: '管理员',
    editor: '编辑者',
    viewer: '观察者',
  }
  return map[role]
}

function getStatusLabel(status: UserStatus): string {
  return status === 'active' ? '启用' : '禁用'
}
</script>

<template>
  <el-table
    :data="users"
    border
    stripe
    style="width: 100%"
    empty-text="暂无数据"
    v-loading="loading"
  >
    <el-table-column prop="username" label="用户名" min-width="120" />
    <el-table-column prop="tenantName" label="所属租户" min-width="140" />
    <el-table-column label="角色" width="100">
      <template #default="{ row }">
        <el-tag :type="getRoleTagType(row.role)" size="small">
          {{ getRoleLabel(row.role) }}
        </el-tag>
      </template>
    </el-table-column>
    <el-table-column prop="email" label="邮箱" min-width="200" />
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
    <el-table-column label="操作" width="160" fixed="right">
      <template #default="{ row }">
        <el-button type="primary" link size="small" @click="emit('edit', (row as User))">
          编辑
        </el-button>
        <el-button type="danger" link size="small" @click="emit('delete', (row as User))">
          删除
        </el-button>
      </template>
    </el-table-column>
  </el-table>
</template>