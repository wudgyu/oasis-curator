<script setup lang="ts">
import { computed, ref, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  HomeFilled,
  UserFilled,
  OfficeBuilding,
  Share,
  SwitchButton,
  MagicStick,
} from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { fetchTenants } from '@/api/tenants'
import type { TenantBrief } from '@/types'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

interface MenuItem {
  path: string
  title: string
  icon: typeof HomeFilled
  /** 仅 admin 可见 */
  adminOnly?: boolean
}

const menuItems: MenuItem[] = [
  { path: '/home', title: '首页', icon: HomeFilled },
  { path: '/tenants', title: '租户管理', icon: OfficeBuilding, adminOnly: true },
  { path: '/orgs', title: '组织管理', icon: Share },
  { path: '/users', title: '用户管理', icon: UserFilled },
  { path: '/iam-config', title: 'IAM 配置生成', icon: MagicStick, adminOnly: true },
]

/** 根据角色过滤菜单：租户管理仅 admin 可见 */
const visibleMenus = computed(() =>
  menuItems.filter((item) => !item.adminOnly || authStore.isAdmin),
)

const activeMenu = computed(() => route.path)

/**
 * 是否显示租户上下文控件（切换器/租户标签）
 * 租户管理页是全局视图（展示所有租户），不按上下文租户隔离，无需显示
 */
const showTenantContext = computed(() => route.path !== '/tenants')

function handleMenuSelect(path: string): void {
  router.push(path)
}

async function handleLogout(): Promise<void> {
  try {
    await ElMessageBox.confirm(
      '确定要退出登录吗？',
      '退出确认',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning',
      },
    )
  } catch {
    // 取消退出
    return
  }

  await authStore.logout()
  router.push('/login')
}

// ---------- admin 租户工作区切换 ----------
const adminTenants = ref<TenantBrief[]>([])
const adminTenantsLoading = ref(false)

async function loadAdminTenants(): Promise<void> {
  if (!authStore.isAdmin) return
  adminTenantsLoading.value = true
  try {
    const result = await fetchTenants({ page: 1, pageSize: 100 })
    adminTenants.value = result.items.map((t) => ({ id: t.id, name: t.name }))
    // 工作区未选择时默认第一个租户
    if (!authStore.currentTenantId && adminTenants.value.length > 0) {
      authStore.switchTenant(adminTenants.value[0].id)
    }
  } catch {
    // 错误提示由拦截器统一处理
  } finally {
    adminTenantsLoading.value = false
  }
}

/** 切换 admin 当前工作区租户 */
function handleTenantSwitch(tenantId: string): void {
  authStore.switchTenant(tenantId)
  const target = adminTenants.value.find((t) => t.id === tenantId)
  ElMessage.success(`已切换到租户「${target?.name ?? tenantId}」`)
}

// admin 登录态就绪后加载租户列表
watch(
  () => authStore.isLoggedIn,
  (loggedIn) => {
    if (loggedIn) loadAdminTenants()
  },
)
onMounted(() => {
  if (authStore.isLoggedIn) loadAdminTenants()
})
</script>

<template>
  <el-container class="app-layout">
    <!-- 侧边栏 -->
    <el-aside width="220px">
      <div class="logo">
        <span class="logo-text">Oasis Curator</span>
        <span class="logo-sub">绿洲馆长</span>
      </div>
      <el-menu
        :default-active="activeMenu"
        background-color="#304156"
        text-color="#bfcbd9"
        active-text-color="#409EFF"
        @select="handleMenuSelect"
      >
        <el-menu-item
          v-for="item in visibleMenus"
          :key="item.path"
          :index="item.path"
        >
          <el-icon><component :is="item.icon" /></el-icon>
          <span>{{ item.title }}</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <!-- 主内容区 -->
    <el-container>
      <el-header height="56px">
        <div class="header-content">
          <span class="header-title">{{ route.meta.title || 'Oasis Curator' }}</span>
          <div class="header-right">
            <!-- 租户切换器：仅平台 admin 可见，位于登录用户与登出按钮之前 -->
            <el-select
              v-if="authStore.isAdmin && showTenantContext"
              :model-value="authStore.currentTenantId"
              size="small"
              style="width: 150px"
              :loading="adminTenantsLoading"
              placeholder="选择租户"
              @change="handleTenantSwitch"
            >
              <el-option
                v-for="t in adminTenants"
                :key="t.id"
                :label="t.name"
                :value="t.id"
              />
            </el-select>
            <span
              v-else-if="authStore.tenantName && showTenantContext"
              class="header-tenant"
            >
              租户：{{ authStore.tenantName }}
            </span>
            <span class="header-org" v-if="authStore.orgName && showTenantContext">
              {{ authStore.orgName }}
            </span>
            <span class="header-user">{{ authStore.username }}</span>
            <el-button
              type="danger"
              :icon="SwitchButton"
              text
              size="small"
              @click="handleLogout"
            >
              退出
            </el-button>
          </div>
        </div>
      </el-header>
      <el-main>
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<style scoped>
.app-layout {
  height: 100vh;
}

.el-aside {
  background-color: #304156;
  overflow: hidden;
}

.logo {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 20px 0 16px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.logo-text {
  font-size: 18px;
  font-weight: 700;
  color: #fff;
  letter-spacing: 1px;
}

.logo-sub {
  font-size: 12px;
  color: #8c98a8;
  margin-top: 4px;
}

.el-menu {
  border-right: none;
}

.el-header {
  background-color: #fff;
  border-bottom: 1px solid #e6e6e6;
  display: flex;
  align-items: center;
}

.header-content {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
}

.header-title {
  font-size: 16px;
  font-weight: 500;
  color: #303133;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.header-tenant {
  font-size: 13px;
  color: #909399;
  padding: 2px 10px;
  background: #f0f2f5;
  border-radius: 4px;
}

.header-org {
  font-size: 13px;
  color: #409eff;
  padding: 2px 10px;
  background: #ecf5ff;
  border-radius: 4px;
}

.header-user {
  font-size: 14px;
  color: #303133;
}

.el-main {
  background-color: #f0f2f5;
  padding: 0;
}
</style>