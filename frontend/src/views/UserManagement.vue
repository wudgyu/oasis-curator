<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Search, RefreshLeft } from '@element-plus/icons-vue'
import type { FormInstance, FormRules } from 'element-plus'
import { useUserStore, useTenantNames } from '@/stores/user'
import type { User, UserFormData, UserRole, UserStatus } from '@/types'

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
const dialogTitle = ref('新增用户')
const isEditing = ref(false)
const editingUserId = ref('')
const formRef = ref<FormInstance>()

const formData = reactive<UserFormData>({
  username: '',
  email: '',
  tenantName: '',
  role: 'viewer',
  status: 'active',
})

const formRules: FormRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 2, max: 20, message: '用户名长度在 2 到 20 个字符', trigger: 'blur' },
  ],
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { type: 'email', message: '请输入正确的邮箱格式', trigger: 'blur' },
  ],
  tenantName: [
    { required: true, message: '请选择租户', trigger: 'change' },
  ],
  role: [
    { required: true, message: '请选择角色', trigger: 'change' },
  ],
}

function openAddDialog(): void {
  dialogTitle.value = '新增用户'
  isEditing.value = false
  editingUserId.value = ''
  formData.username = ''
  formData.email = ''
  formData.tenantName = ''
  formData.role = 'viewer'
  formData.status = 'active'
  dialogVisible.value = true
}

function openEditDialog(user: User): void {
  dialogTitle.value = '编辑用户'
  isEditing.value = true
  editingUserId.value = user.id
  formData.username = user.username
  formData.email = user.email
  formData.tenantName = user.tenantName
  formData.role = user.role
  formData.status = user.status
  dialogVisible.value = true
}

async function handleSubmit(): Promise<void> {
  if (!formRef.value) return

  try {
    await formRef.value.validate()

    if (isEditing.value) {
      userStore.updateUser(editingUserId.value, { ...formData })
      ElMessage.success('用户信息更新成功')
    } else {
      userStore.addUser({ ...formData })
      ElMessage.success('用户创建成功')
    }

    dialogVisible.value = false
  } catch {
    // 表单校验不通过，不做任何操作
  }
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

// 对话框关闭后重置表单校验状态
function handleDialogClosed(): void {
  formRef.value?.resetFields()
}

// ---------- 角色标签样式 ----------
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

// ---------- 初始化 ----------
onMounted(() => {
  userStore.updatePaginationTotal()
})
</script>

<template>
  <div class="user-management">
    <!-- 页面标题 -->
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

    <!-- 用户列表表格 -->
    <el-table
      :data="userStore.pagedUsers"
      border
      stripe
      style="width: 100%"
      empty-text="暂无数据"
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
          <el-button type="primary" link size="small" @click="openEditDialog(row)">
            编辑
          </el-button>
          <el-button type="danger" link size="small" @click="handleDelete(row)">
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

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

    <!-- 新增/编辑对话框 -->
    <el-dialog
      v-model="dialogVisible"
      :title="dialogTitle"
      width="520px"
      :close-on-click-modal="false"
      @closed="handleDialogClosed"
    >
      <el-form
        ref="formRef"
        :model="formData"
        :rules="formRules"
        label-width="90px"
        status-icon
      >
        <el-form-item label="用户名" prop="username">
          <el-input
            v-model="formData.username"
            placeholder="请输入用户名"
            maxlength="20"
            show-word-limit
          />
        </el-form-item>
        <el-form-item label="邮箱" prop="email">
          <el-input
            v-model="formData.email"
            placeholder="请输入邮箱地址"
          />
        </el-form-item>
        <el-form-item label="所属租户" prop="tenantName">
          <el-select
            v-model="formData.tenantName"
            placeholder="请选择租户"
            style="width: 100%"
          >
            <el-option
              v-for="name in tenantNames"
              :key="name"
              :label="name"
              :value="name"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="角色" prop="role">
          <el-select
            v-model="formData.role"
            placeholder="请选择角色"
            style="width: 100%"
          >
            <el-option label="管理员 (admin)" value="admin" />
            <el-option label="编辑者 (editor)" value="editor" />
            <el-option label="观察者 (viewer)" value="viewer" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-radio-group v-model="formData.status">
            <el-radio value="active">启用</el-radio>
            <el-radio value="disabled">禁用</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSubmit">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.user-management {
  padding: 24px;
  max-width: 1400px;
  margin: 0 auto;
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