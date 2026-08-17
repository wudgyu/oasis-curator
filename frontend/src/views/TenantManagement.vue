<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Plus, Search, RefreshLeft } from '@element-plus/icons-vue'
import { useTenantStore } from '@/stores/tenant'
import type { Tenant, TenantFormData, TenantPlan, TenantStatus } from '@/types'
import TenantTable from '@/components/TenantTable.vue'
import TenantFormDialog from '@/components/TenantFormDialog.vue'

/**
 * 租户管理页面（对接 FastAPI 后端）
 * - 数据通过 Axios 从 /api/tenants 获取（服务端分页）
 * - 仅 admin 角色可访问（路由守卫 + 后端 require_admin 双重校验）
 */

// ---------- Store ----------
const tenantStore = useTenantStore()

// ---------- 筛选条件 ----------
const filterName = ref('')
const filterPlan = ref<TenantPlan | ''>('')
const filterStatus = ref<TenantStatus | ''>('')

function handleSearch(): void {
  tenantStore.setFilter({
    name: filterName.value,
    plan: filterPlan.value,
    status: filterStatus.value,
  })
}

function handleReset(): void {
  filterName.value = ''
  filterPlan.value = ''
  filterStatus.value = ''
  tenantStore.resetFilter()
}

// ---------- 分页 ----------
function handlePageChange(page: number): void {
  tenantStore.setPage(page)
}

function handleSizeChange(size: number): void {
  tenantStore.setPageSize(size)
}

// ---------- 对话框 ----------
const dialogVisible = ref(false)
const dialogIsEditing = ref(false)
const editingTenantId = ref('')
const dialogInitialData = ref<TenantFormData | undefined>(undefined)

function openAddDialog(): void {
  dialogIsEditing.value = false
  editingTenantId.value = ''
  dialogInitialData.value = undefined
  dialogVisible.value = true
}

function openEditDialog(tenant: Tenant): void {
  dialogIsEditing.value = true
  editingTenantId.value = tenant.id
  dialogInitialData.value = {
    name: tenant.name,
    plan: tenant.plan,
    status: tenant.status,
  }
  dialogVisible.value = true
}

async function handleDialogConfirm(data: TenantFormData): Promise<void> {
  try {
    if (dialogIsEditing.value) {
      await tenantStore.editTenant(editingTenantId.value, data)
      ElMessage.success('租户信息更新成功')
    } else {
      await tenantStore.addTenant(data)
      ElMessage.success('租户创建成功')
    }
    dialogVisible.value = false
  } catch {
    // 错误提示由 Axios 拦截器统一处理
  }
}

function handleDialogCancel(): void {
  dialogVisible.value = false
}

function handleDelete(tenant: Tenant): void {
  ElMessageBox.confirm(
    `确定要删除租户「${tenant.name}」吗？该租户下的所有用户将失去归属。此操作不可撤销。`,
    '删除确认',
    {
      confirmButtonText: '确定删除',
      cancelButtonText: '取消',
      type: 'warning',
    },
  )
    .then(async () => {
      try {
        await tenantStore.removeTenant(tenant.id)
        ElMessage.success(`已删除租户「${tenant.name}」`)
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
  // 进入页面时重置筛选，避免上次浏览的筛选条件残留
  tenantStore.resetFilter()
})
</script>

<template>
  <div class="tenant-management">
    <div class="page-header">
      <h1>租户管理</h1>
      <el-button type="primary" :icon="Plus" @click="openAddDialog">
        新增租户
      </el-button>
    </div>

    <!-- 搜索筛选栏 -->
    <div class="filter-bar">
      <el-input
        v-model="filterName"
        placeholder="按租户名称搜索"
        clearable
        style="width: 200px"
        @clear="handleSearch"
        @keyup.enter="handleSearch"
      />
      <el-select
        v-model="filterPlan"
        placeholder="按套餐筛选"
        clearable
        style="width: 140px"
        @change="handleSearch"
        @clear="handleSearch"
      >
        <el-option label="基础版" value="basic" />
        <el-option label="专业版" value="pro" />
        <el-option label="企业版" value="enterprise" />
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

    <!-- 租户表格 -->
    <TenantTable
      :tenants="tenantStore.tenants"
      :loading="tenantStore.loading"
      @edit="openEditDialog"
      @delete="handleDelete"
    />

    <!-- 分页 -->
    <div class="pagination-wrapper">
      <el-pagination
        v-model:current-page="tenantStore.page"
        v-model:page-size="tenantStore.pageSize"
        :page-sizes="[5, 10, 20, 50]"
        :total="tenantStore.total"
        layout="total, sizes, prev, pager, next, jumper"
        background
        @current-change="handlePageChange"
        @size-change="handleSizeChange"
      />
    </div>

    <!-- 租户表单对话框 -->
    <TenantFormDialog
      :visible="dialogVisible"
      :is-editing="dialogIsEditing"
      :initial-data="dialogInitialData"
      @confirm="handleDialogConfirm"
      @cancel="handleDialogCancel"
    />
  </div>
</template>

<style scoped>
.tenant-management {
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