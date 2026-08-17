<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  HomeFilled,
  UserFilled,
  OfficeBuilding,
  SwitchButton,
} from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'

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
  { path: '/users', title: '用户管理', icon: UserFilled },
]

/** 根据角色过滤菜单：租户管理仅 admin 可见 */
const visibleMenus = computed(() =>
  menuItems.filter((item) => !item.adminOnly || authStore.isAdmin),
)

const activeMenu = computed(() => route.path)

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

/** 切换当前上下文租户 */
function handleTenantSwitch(tenantId: string): void {
  authStore.switchTenant(tenantId)
  ElMessage.success(`已切换到租户「${authStore.currentTenantName}」`)
}
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
            <!-- 租户切换器：可访问租户大于 1 个时显示，位于导航栏最右侧 -->
            <el-select
              v-if="authStore.canSwitchTenant"
              :model-value="authStore.currentTenantId"
              size="small"
              style="width: 150px"
              @change="handleTenantSwitch"
            >
              <el-option
                v-for="t in authStore.accessibleTenants"
                :key="t.id"
                :label="t.name"
                :value="t.id"
              />
            </el-select>
            <span v-else-if="authStore.currentTenantName" class="header-tenant">
              租户：{{ authStore.currentTenantName }}
            </span>
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

.header-user {
  font-size: 14px;
  color: #303133;
}

.el-main {
  background-color: #f0f2f5;
  padding: 0;
}
</style>