<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { UserFilled, OfficeBuilding, DataAnalysis } from '@element-plus/icons-vue'
import { useUserStore, useTenantNames } from '@/stores/user'

/**
 * 首页 / 仪表盘
 * 展示平台核心数据概览，后续对接后端 API 获取真实统计数据
 */

const userStore = useUserStore()
const tenantNames = useTenantNames()

interface StatCard {
  title: string
  value: number
  unit: string
  icon: typeof UserFilled
  color: string
}

const stats = ref<StatCard[]>([])

onMounted(() => {
  stats.value = [
    {
      title: '用户总数',
      value: userStore.users.length,
      unit: '人',
      icon: UserFilled,
      color: '#409EFF',
    },
    {
      title: '租户数量',
      value: tenantNames.length,
      unit: '个',
      icon: OfficeBuilding,
      color: '#67C23A',
    },
    {
      title: '在线用户',
      value: userStore.users.filter((u) => u.status === 'active').length,
      unit: '人',
      icon: DataAnalysis,
      color: '#E6A23C',
    },
  ]
})
</script>

<template>
  <div class="home-page">
    <h2>平台概览</h2>

    <!-- 统计卡片 -->
    <div class="stats-grid">
      <el-card
        v-for="stat in stats"
        :key="stat.title"
        class="stat-card"
        shadow="hover"
      >
        <div class="stat-content">
          <div class="stat-info">
            <span class="stat-title">{{ stat.title }}</span>
            <span class="stat-value">
              {{ stat.value }}
              <small>{{ stat.unit }}</small>
            </span>
          </div>
          <div class="stat-icon" :style="{ backgroundColor: stat.color }">
            <el-icon :size="28">
              <component :is="stat.icon" />
            </el-icon>
          </div>
        </div>
      </el-card>
    </div>

    <!-- 快速入口 -->
    <el-card class="quick-actions" shadow="never">
      <template #header>
        <span>快速入口</span>
      </template>
      <div class="action-list">
        <el-button type="primary" plain @click="$router.push('/tenants')">
          租户管理
        </el-button>
        <el-button type="primary" plain @click="$router.push('/users')">
          用户管理
        </el-button>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.home-page {
  padding: 24px;
  max-width: 1200px;
}

.home-page h2 {
  margin: 0 0 20px;
  font-size: 20px;
  font-weight: 600;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}

.stat-card {
  cursor: default;
}

.stat-content {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.stat-info {
  display: flex;
  flex-direction: column;
}

.stat-title {
  font-size: 14px;
  color: #909399;
  margin-bottom: 8px;
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: #303133;
}

.stat-value small {
  font-size: 14px;
  font-weight: 400;
  color: #909399;
}

.stat-icon {
  width: 56px;
  height: 56px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
}

.quick-actions {
  max-width: 600px;
}

.action-list {
  display: flex;
  gap: 12px;
}
</style>