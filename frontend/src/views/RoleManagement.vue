<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete, View } from '@element-plus/icons-vue'
import VueJsonPretty from 'vue-json-pretty'
import 'vue-json-pretty/lib/styles.css'
import { fetchIamRoles, deleteIamRole } from '@/api/iam'
import type { IamRoleItem } from '@/types'

/**
 * 角色管理页面
 *
 * 展示当前租户可见的所有角色：
 * - 内置角色（不可删除，无权限细节）
 * - 自定义角色（由 IAM 配置生成器创建，含完整 RBAC 2.0 配置）
 */

const roles = ref<IamRoleItem[]>([])
const loading = ref(false)
const detailVisible = ref(false)
const selectedRole = ref<IamRoleItem | null>(null)

onMounted(async () => {
  await loadRoles()
})

async function loadRoles(): Promise<void> {
  loading.value = true
  try {
    roles.value = await fetchIamRoles()
  } catch {
    ElMessage.error('加载角色列表失败')
  } finally {
    loading.value = false
  }
}

function showDetail(row: Record<string, unknown>): void {
  const role = row as unknown as IamRoleItem
  selectedRole.value = role
  detailVisible.value = true
}

async function handleDelete(row: Record<string, unknown>): Promise<void> {
  const role = row as unknown as IamRoleItem
  try {
    await ElMessageBox.confirm(
      `确定要删除自定义角色「${role.name}」吗？删除后不可恢复。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '确定删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }

  try {
    await deleteIamRole(role.id)
    ElMessage.success(`角色「${role.name}」已删除`)
    await loadRoles()
  } catch {
    ElMessage.error('删除失败，请稍后重试')
  }
}

/** 角色类型标签（接受模板泛型行，内部安全访问） */
function roleTypeTag(row: Record<string, unknown>): '内置' | '自定义' {
  return (row as unknown as IamRoleItem).builtin ? '内置' : '自定义'
}

function roleTypeColor(row: Record<string, unknown>): 'info' | 'success' {
  return (row as unknown as IamRoleItem).builtin ? 'info' : 'success'
}
</script>

<template>
  <div class="role-management">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span class="card-title">角色管理</span>
          <span class="card-subtitle">
            内置角色由系统预置，自定义角色通过
            <el-link type="primary" href="#/iam-config">IAM 配置生成器</el-link>
            创建
          </span>
        </div>
      </template>

      <el-table
        v-loading="loading"
        :data="roles"
        stripe
        empty-text="暂无角色数据"
      >
        <el-table-column prop="code" label="角色编码" min-width="140" />
        <el-table-column prop="name" label="角色名称" min-width="120" />
        <el-table-column prop="description" label="描述" min-width="200">
          <template #default="{ row }">
            {{ row.description || '-' }}
          </template>
        </el-table-column>
        <el-table-column label="类型" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="roleTypeColor(row)" size="small">
              {{ roleTypeTag(row) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="权限配置" width="100" align="center">
          <template #default="{ row }">
            <el-button
              v-if="!row.builtin"
              :icon="View"
              text
              size="small"
              type="primary"
              @click="showDetail(row)"
            >
              查看
            </el-button>
            <span v-else class="text-muted">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" min-width="170">
          <template #default="{ row }">
            {{ new Date(row.created_at).toLocaleString('zh-CN') }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80" align="center" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="!row.builtin"
              :icon="Delete"
              text
              size="small"
              type="danger"
              @click="handleDelete(row)"
            />
            <span v-else class="text-muted">-</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 角色详情弹窗 -->
    <el-dialog
      v-model="detailVisible"
      :title="`角色详情：${selectedRole?.name ?? ''}`"
      width="640px"
      destroy-on-close
    >
      <template v-if="selectedRole">
        <el-descriptions :column="2" border size="small" class="detail-desc">
          <el-descriptions-item label="角色编码">{{ selectedRole.code }}</el-descriptions-item>
          <el-descriptions-item label="角色名称">{{ selectedRole.name }}</el-descriptions-item>
          <el-descriptions-item label="描述" :span="2">
            {{ selectedRole.description || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="类型">
            <el-tag :type="roleTypeColor(selectedRole)" size="small">
              {{ roleTypeTag(selectedRole) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="创建时间">
            {{ new Date(selectedRole.created_at).toLocaleString('zh-CN') }}
          </el-descriptions-item>
        </el-descriptions>

        <div v-if="selectedRole.permissions && selectedRole.permissions.length > 0" class="detail-section">
          <h4 class="section-title">权限列表</h4>
          <div class="json-block">
            <vue-json-pretty
              :data="selectedRole.permissions"
              :deep="3"
              :show-line="false"
              :show-double-quotes="true"
            />
          </div>
        </div>

        <div v-if="selectedRole.data_scope" class="detail-section">
          <h4 class="section-title">数据范围</h4>
          <div class="json-block">
            <vue-json-pretty
              :data="selectedRole.data_scope"
              :deep="3"
              :show-line="false"
              :show-double-quotes="true"
            />
          </div>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.role-management {
  padding: 16px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.card-title {
  font-size: 16px;
  font-weight: 600;
}

.card-subtitle {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.text-muted {
  color: var(--el-text-color-placeholder);
  font-size: 13px;
}

.detail-desc {
  margin-bottom: 16px;
}

.detail-section {
  margin-top: 16px;
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  margin: 0 0 8px;
  color: var(--el-text-color-primary);
}

.json-block {
  background-color: var(--el-fill-color-light);
  border-radius: 6px;
  padding: 12px;
  max-height: 300px;
  overflow: auto;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
}
</style>