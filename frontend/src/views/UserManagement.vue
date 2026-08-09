<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Search, RefreshLeft } from '@element-plus/icons-vue'
import { useUserStore, useTenantNames } from '@/stores/user'
import type { User, UserFormData, UserRole } from '@/types'
import UserTable from '@/components/UserTable.vue'
import UserFormDialog from '@/components/UserFormDialog.vue'

/**
 * 用户管理页面
 * 使用提取的 UserTable 和 UserFormDialog 组件，
 * 通过 defineProps<T> / defineEmits<T> 进行组件通信
 */

// ---------- Store ----------
const userStore = useUserStore()
const tenantNames = useTenantNames()

// ---------- 筛选条件 ----------
const filterUsername = ref('')
const filterRole = ref<UserRole | ''>('')
const filterTenant = ref('')

function handleSearch(): void {
  userStore.setFilter({
    username: filterUsername.value,
    role: filterRole.value,
    tenantName: filterTenant.value,
  })
}

function handleReset(): void {
  filterUsername.value = ''
  filterRole.value = ''
  filterTenant.value = ''
  userStore.resetFilter()
}

// ---------- 分页 ----------
const currentPage = ref(1)
const pageSize = ref(10)

function handlePageChange(page: number): void {
  currentPage.value = page
  userStore.setPage(page)
}

function handleSizeChange(size: number): void {
  pageSize.value = size
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
    tenantName: user.tenantName,
    role: user.role,
    status: user.status,
  }
  dialogVisible.value = true
}

function handleDialogConfirm(data: UserFormData): void {
  if (dialogIsEditing.value) {
    userStore.updateUser(editingUserId.value, data)
    ElMessage.success('用户信息更新成功')
  } else {
    userStore.addUser(data)
    ElMessage.success('用户创建成功')
  }
  dialogVisible.value = false
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
    .then(() => {
      userStore.deleteUser(user.id)
      ElMessage.success(`已删除用户「${user.username}」`)
    })
    .catch(() => {
      // 用户取消删除
    })
}

// ---------- 初始化 ----------
onMounted(() => {
  userStore.updatePaginationTotal()
})
</script>

<template>
  <div class="user-management">
    <div class="page-header">
      <h1>用户管理</h1>
      <el-button type="primary" :icon="Plus" @click="openAddDialog">
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
        v-model="filterTenant"
        placeholder="按租户筛选"
        clearable
        style="width: 160px"
        @change="handleSearch"
        @clear="handleSearch"
      >
        <el-option
          v-for="name in tenantNames"
          :key="name"
          :label="name"
          :value="name"
        />
      </el-select>
      <el-button type="primary" :icon="Search" @click="handleSearch">
        搜索
      </el-button>
      <el-button :icon="RefreshLeft" @click="handleReset">重置</el-button>
    </div>

    <!-- 用户表格（提取的组件，使用 defineProps / defineEmits） -->
    <UserTable
      :users="userStore.pagedUsers"
      @edit="openEditDialog"
      @delete="handleDelete"
    />

    <!-- 分页 -->
    <div class="pagination-wrapper">
      <el-pagination
        v-model:current-page="currentPage"
        v-model:page-size="pageSize"
        :page-sizes="[5, 10, 20, 50]"
        :total="userStore.filteredUsers.length"
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
      :tenant-names="tenantNames"
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