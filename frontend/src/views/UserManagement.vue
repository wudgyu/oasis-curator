<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { Plus, Search, RefreshLeft } from '@element-plus/icons-vue'
import { useUserStore } from '@/stores/user'
import { useAuthStore } from '@/stores/auth'
import { fetchOrgTree } from '@/api/orgs'
import { fetchRoles } from '@/api/roles'
import type { User, UserFormData, RoleCode, OrgTreeNode, RoleOption } from '@/types'
import UserTable from '@/components/UserTable.vue'
import UserFormDialog from '@/components/UserFormDialog.vue'

/**
 * 用户管理页面（对接 FastAPI 后端，RBAC 数据范围）
 * - 列表按当前用户角色的数据范围过滤（后端处理）
 * - 写权限：admin（上下文租户全量）/ manager（本组织子树内）
 * - admin 切换租户工作区时自动刷新
 */

// ---------- Store ----------
const userStore = useUserStore()
const authStore = useAuthStore()

// ---------- 筛选条件 ----------
const filterUsername = ref('')
const filterRole = ref<RoleCode | ''>('')
const filterStatus = ref('')
const filterOrgId = ref('')

function handleSearch(): void {
  userStore.setFilter({
    username: filterUsername.value,
    role: filterRole.value,
    status: filterStatus.value as User['status'] | '',
    orgId: filterOrgId.value,
  })
}

function handleReset(): void {
  filterUsername.value = ''
  filterRole.value = ''
  filterStatus.value = ''
  filterOrgId.value = ''
  userStore.resetFilter()
}

// ---------- 分页 ----------
function handlePageChange(page: number): void {
  userStore.setPage(page)
}

function handleSizeChange(size: number): void {
  userStore.setPageSize(size)
}

// ---------- 组织树与角色 ----------
const orgTree = ref<OrgTreeNode[]>([])
const roleOptions = ref<RoleOption[]>([])

/** 管理器可选的组织树（限其子树） */
const scopedOrgTree = computed<OrgTreeNode[]>(() => {
  // admin 全树
  if (authStore.isAdmin) return orgTree.value
  // manager、auditor 子树
  if (authStore.roleCode === 'manager' || authStore.roleCode === 'auditor') {
    return filterTreeByPath(orgTree.value, authStore.orgPath)
  }
  // employee 组织单节点
  const pathNode = filterTreeOnlyPath(orgTree.value, authStore.orgPath);
  return pathNode == null ? [] : [pathNode]
})

function filterTreeByPath(nodes: OrgTreeNode[], prefix: string): OrgTreeNode[] {
  const result: OrgTreeNode[] = []
  // 递归遍历组织树
  for (const n of nodes) {
    // 目标path不在当前树上，直接返回
    if (!prefix.startsWith(n.path)) {
      continue
    }

    // 当前根节点path符合目标path，则整树添加
    if (n.path.startsWith(prefix)) {
      result.push({ ...n, children: n.children })
    }
    // 否则递归检查子节点
    else {
      const subTree: OrgTreeNode[] = filterTreeByPath(n.children, prefix);
      // 如果匹配到目标path，则截断树返回
      if (subTree.length > 0) {
        const subRoot = subTree[0]
        result.push({ ...subRoot, children: subRoot.children })
      }
    }
  }
  return result
}

function filterTreeOnlyPath(nodes: OrgTreeNode[], prefix: string): OrgTreeNode | null {
  for (const n of nodes) {
    // 目标path不在当前树上，直接返回
    if (!prefix.startsWith(n.path)) {
      break
    }
    // 当前根节点path符合目标path，则添加节点
    if (n.path == prefix) {
      return { ...n }
    }
    // 否则递归检查子节点
    else {
      const targetNode = filterTreeOnlyPath(n.children, prefix)
      if (targetNode != null) {
        return { ...targetNode }
      }
    }
  }
  return null
}

async function loadOrgData(): Promise<void> {
  try {
    const [treeData, roles] = await Promise.all([fetchOrgTree(), fetchRoles()])
    orgTree.value = treeData
    roleOptions.value = roles
  } catch {
    // 错误提示由拦截器统一处理
  }
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
    orgId: user.org.id,
    roleCode: user.roleCode as UserFormData['roleCode'],
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
  // 进入页面时重置筛选，避免上次浏览的筛选条件残留导致列表与统计不一致
  userStore.resetFilter()
  loadOrgData()
})

// admin 切换租户工作区后自动刷新
watch(
  () => authStore.currentTenantId,
  (newId) => {
    if (!authStore.isLoggedIn || !newId) return
    filterUsername.value = ''
    filterRole.value = ''
    filterStatus.value = ''
    filterOrgId.value = ''
    userStore.resetFilter()
    loadOrgData()
  },
)
</script>

<template>
  <div class="user-management">
    <div class="page-header">
      <h1>用户管理</h1>
      <el-button
        v-if="authStore.canWrite"
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
        style="width: 130px"
        @change="handleSearch"
        @clear="handleSearch"
      >
        <el-option
          v-for="r in roleOptions"
          :key="r.code"
          :label="r.name"
          :value="r.code"
        />
      </el-select>
      <el-select
        v-model="filterStatus"
        placeholder="按状态筛选"
        clearable
        style="width: 130px"
        @change="handleSearch"
        @clear="handleSearch"
      >
        <el-option label="启用" value="active" />
        <el-option label="禁用" value="disabled" />
      </el-select>
      <el-tree-select
        v-model="filterOrgId"
        :data="scopedOrgTree"
        node-key="id"
        :props="{ label: 'name', children: 'children' }"
        check-strictly
        default-expand-all
        :render-after-expand="false"
        placeholder="按组织筛选（含子树）"
        clearable
        style="width: 200px"
        @change="handleSearch"
      />
      <el-button type="primary" :icon="Search" @click="handleSearch">
        搜索
      </el-button>
      <el-button :icon="RefreshLeft" @click="handleReset">重置</el-button>
    </div>

    <!-- 用户表格（提取的组件，使用 defineProps / defineEmits） -->
    <UserTable
      :users="userStore.users"
      :loading="userStore.loading"
      :show-actions="authStore.canWrite"
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
      :org-tree="scopedOrgTree"
      :role-options="roleOptions"
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