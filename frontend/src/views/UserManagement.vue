<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Plus, Search, RefreshLeft } from '@element-plus/icons-vue'
import { useUserStore } from '@/stores/user'
import { useAuthStore } from '@/stores/auth'
import type { User, UserFormData, UserRole } from '@/types'
import UserTable from '@/components/UserTable.vue'
import UserFormDialog from '@/components/UserFormDialog.vue'

/**
 * 用户管理页面（对接 FastAPI 后端）
 * - 数据通过 Axios 从 /api/users 获取（服务端分页 + 租户隔离）
 * - admin 可新增/编辑/删除；editor/viewer 只读
 */

// ---------- Store ----------
const userStore = useUserStore()
const authStore = useAuthStore()

// ---------- 筛选条件 ----------
const filterUsername = ref('')
const filterRole = ref<UserRole | ''>('')
const filterStatus = ref('')

function handleSearch(): void {
  userStore.setFilter({
    username: filterUsername.value,
    role: filterRole.value,
    status: filterStatus.value as User['status'] | '',
  })
}

function handleReset(): void {
  filterUsername.value = ''
  filterRole.value = ''
  filterStatus.value = ''
  userStore.resetFilter()
}

// ---------- 分页 ----------
function handlePageChange(page: number): void {
  userStore.setPage(page)
}

function handleSizeChange(size: number): void {
  userStore.setPageSize(size)
}

// ---------- 对话框 ----------
const dialogVisible = ref(false)
const dialogIsEditing = ref(false)
const editingUserId = ref('')
const dialogInitialData = ref<UserFormData | undefined>(undefined)

function openAddDialog(): void {
  dialogIsEditing.value = false
  editingUserId.value = ''
  dialogInitialData.value = undefined
  dialogVisible.value = true
}

function openEditDialog(user: User): void {
  dialogIsEditing.value = true
  editingUserId.value = user.id
  dialogInitialData.value = {
    username: user.username,
    email: user.email,
    password: '',
    role: user.role,
    status: user.status,
  }
  dialogVisible.value = true
}

async function handleDialogConfirm(data: UserFormData): Promise<void> {
  try {
    if (dialogIsEditing.value) {
      // 编辑时密码留空表示不修改
      const payload: Partial<UserFormData> = { ...data }
      if (!payload.password) {
        delete payload.password
      }
      await userStore.editUser(editingUserId.value, payload)
      ElMessage.success('用户信息更新成功')
    } else {
      await userStore.addUser(data)
      ElMessage.success('用户创建成功')
    }
    dialogVisible.value = false
  } catch {
    // 错误提示由 Axios 拦截器统一处理
  }
}

function handleDialogCancel(): void {
  dialogVisible.value = false
}

function handleDelete(user: User): void {
  ElMessageBox.confirm(
    `确定要删除用户「${user.username}」吗？此操作不可撤销。`,
    '删除确认',
    {
      confirmButtonText: '确定删除',
      cancelButtonText: '取消',
      type: 'warning',
    },
  )
    .then(async () => {
      try {
        await userStore.removeUser(user.id)
        ElMessage.success(`已删除用户「${user.username}」`)
      } catch {
        // 错误提示由 Axios 拦截器统一处理
      }
    })
    .catch(() => {
      // 用户取消删除
    })
}

// ---------- 初始化 ----------
onMounted(() => {
  userStore.fetchUserList()
})
</script>

<template>
  <div class="user-management">
    <div class="page-header">
      <h1>用户管理</h1>
      <el-button
        v-if="authStore.isAdmin"
        type="primary"
        :icon="Plus"
        @click="openAddDialog"
      >
        新增用户
      </el-button>
    </div>

    <!-- 搜索筛选栏 -->
    <div class="filter-bar">
      <el-input
        v-model="filterUsername"
        placeholder="按用户名搜索"
        clearable
        style="width: 200px"
        @clear="handleSearch"
        @keyup.enter="handleSearch"
      />
      <el-select
        v-model="filterRole"
        placeholder="按角色筛选"
        clearable
        style="width: 140px"
        @change="handleSearch"
        @clear="handleSearch"
      >
        <el-option label="管理员" value="admin" />
        <el-option label="编辑者" value="editor" />
        <el-option label="观察者" value="viewer" />
      </el-select>
      <el-select
        v-model="filterStatus"
        placeholder="按状态筛选"
        clearable
        style="width: 140px"
        @change="handleSearch"
        @clear="handleSearch"
      >
        <el-option label="启用" value="active" />
        <el-option label="禁用" value="disabled" />
      </el-select>
      <el-button type="primary" :icon="Search" @click="handleSearch">
        搜索
      </el-button>
      <el-button :icon="RefreshLeft" @click="handleReset">重置</el-button>
    </div>

    <!-- 用户表格（提取的组件，使用 defineProps / defineEmits） -->
    <UserTable
      :users="userStore.users"
      :loading="userStore.loading"
      :show-actions="authStore.isAdmin"
      @edit="openEditDialog"
      @delete="handleDelete"
    />

    <!-- 分页 -->
    <div class="pagination-wrapper">
      <el-pagination
        v-model:current-page="userStore.page"
        v-model:page-size="userStore.pageSize"
        :page-sizes="[5, 10, 20, 50]"
        :total="userStore.total"
        layout="total, sizes, prev, pager, next, jumper"
        background
        @current-change="handlePageChange"
        @size-change="handleSizeChange"
      />
    </div>

    <!-- 用户表单对话框（提取的组件，使用 defineProps / defineEmits） -->
    <UserFormDialog
      :visible="dialogVisible"
      :is-editing="dialogIsEditing"
      :initial-data="dialogInitialData"
      @confirm="handleDialogConfirm"
      @cancel="handleDialogCancel"
    />
  </div>
</template>

<style scoped>
.user-management {
  padding: 24px;
  max-width: 1400px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.page-header h1 {
  margin: 0;
  font-size: 22px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.filter-bar {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.pagination-wrapper {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>