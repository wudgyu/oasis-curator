<script setup lang="ts">
import type { User, RoleCode, UserStatus } from '@/types'

/**
 * 用户表格组件
 * 展示 defineProps<T>() 和 defineEmits<T>() 的 TypeScript 泛型用法
 */

// ---------- Props ----------
const props = withDefaults(defineProps<{
  /** 用户数据列表 */
  users: User[]
  /** 是否加载中 */
  loading?: boolean
  /** 是否显示操作列（employee / auditor 隐藏编辑/删除按钮） */
  showActions?: boolean
}>(), {
  showActions: true,
})

// ---------- Emits ----------
const emit = defineEmits<{
  /** 编辑用户 */
  (e: 'edit', user: User): void
  /** 删除用户 */
  (e: 'delete', user: User): void
}>()

// ---------- 辅助函数 ----------
function getRoleTagType(role: RoleCode): 'danger' | 'warning' | 'info' {
  const map: Record<RoleCode, 'danger' | 'warning' | 'info'> = {
    admin: 'danger',
    manager: 'danger',
    auditor: 'warning',
    employee: 'info',
  }
  return map[role]
}

function getRoleLabel(role: RoleCode): string {
  const map: Record<RoleCode, string> = {
    admin: '平台管理员',
    manager: '经理',
    auditor: '审计员',
    employee: '员工',
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
    <el-table-column prop="username" label="用户名" min-width="110" />
    <el-table-column prop="org.name" label="所属组织" min-width="120" />
    <el-table-column label="角色" width="100">
      <template #default="{ row }">
        <el-tag :type="getRoleTagType(row.roleCode)" size="small">
          {{ getRoleLabel(row.roleCode) }}
        </el-tag>
      </template>
    </el-table-column>
    <el-table-column prop="email" label="邮箱" min-width="190" />
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
    <el-table-column prop="createdAt" label="创建时间" width="170" />
    <el-table-column v-if="props.showActions" label="操作" width="150" fixed="right">
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