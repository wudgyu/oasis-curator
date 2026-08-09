<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  HomeFilled,
  UserFilled,
} from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()

interface MenuItem {
  path: string
  title: string
  icon: typeof HomeFilled
}

const menuItems: MenuItem[] = [
  { path: '/home', title: '首页', icon: HomeFilled },
  { path: '/users', title: '用户管理', icon: UserFilled },
]

const activeMenu = computed(() => route.path)

function handleMenuSelect(path: string): void {
  router.push(path)
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
          v-for="item in menuItems"
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
  width: 100%;
}

.header-title {
  font-size: 16px;
  font-weight: 500;
  color: #303133;
}

.el-main {
  background-color: #f0f2f5;
  padding: 0;
}
</style>