<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { UserFilled, OfficeBuilding, DataAnalysis } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { fetchUsers } from '@/api/users'
import { fetchTenants } from '@/api/tenants'

/**
 * 首页 / 仪表盘
 * 统计范围 = 当前用户角色的数据范围（后端自动过滤）：
 * - employee：本组织
 * - auditor / manager：本组织 + 子组织
 * - admin：上下文租户（X-Tenant-Id）
 */

const authStore = useAuthStore()

interface StatCard {
  title: string
  subtitle: string
  value: number
  unit: string
  icon: typeof UserFilled
  color: string
}

const stats = ref<StatCard[]>([])
const statsLoading = ref(true)

/** 当前统计范围描述 */
const scopeLabel = computed(() => {
  if (authStore.isAdmin) {
    return authStore.tenantName || '上下文租户'
  }
  if (authStore.roleCode === 'manager') {
    return `${authStore.orgName}（含子组织）`
  }
  if (authStore.roleCode === 'auditor') {
    return `${authStore.orgName}（含子组织）`
  }
  return authStore.orgName || '本组织'
})

async function loadStats(): Promise<void> {
  statsLoading.value = true
  try {
    // 并行获取当前范围内的统计数据（后端按角色范围过滤）
    const [userTotal, activeUserTotal] = await Promise.all([
      fetchUsers({ page: 1, pageSize: 1 }),
      fetchUsers({ page: 1, pageSize: 1, status: 'active' }),
    ])

    const cards: StatCard[] = [
      {
        title: '用户总数',
        subtitle: scopeLabel.value,
        value: userTotal.total,
        unit: '人',
        icon: UserFilled,
        color: '#409EFF',
      },
      {
        title: '启用用户',
        subtitle: scopeLabel.value,
        value: activeUserTotal.total,
        unit: '人',
        icon: DataAnalysis,
        color: '#E6A23C',
      },
    ]

    // 租户统计仅 admin 可见
    if (authStore.isAdmin) {
      const tenantTotal = await fetchTenants({ page: 1, pageSize: 1 })
      cards.unshift({
        title: '租户数量',
        subtitle: '平台全局',
        value: tenantTotal.total,
        unit: '个',
        icon: OfficeBuilding,
        color: '#67C23A',
      })
    }

    stats.value = cards
  } finally {
    statsLoading.value = false
  }
}

onMounted(loadStats)

// admin 切换工作区租户后自动刷新统计
// 登出会清空 currentTenantId，此时不再发起请求（否则产生无凭证的 403 请求）
watch(() => authStore.currentTenantId, (newId) => {
  if (authStore.isLoggedIn && newId) {
    loadStats()
  }
})
</script>

<template>
  <div class="home-page">
    <h2>平台概览</h2>

    <!-- 统计卡片 -->
    <div class="stats-grid" v-loading="statsLoading">
      <el-card
        v-for="stat in stats"
        :key="stat.title"
        class="stat-card"
        shadow="hover"
      >
        <div class="stat-content">
          <div class="stat-info">
            <span class="stat-title">
              {{ stat.title }}
              <small class="stat-scope">{{ stat.subtitle }}</small>
            </span>
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
        <el-button
          v-if="authStore.isAdmin"
          type="primary"
          plain
          @click="$router.push('/tenants')"
        >
          租户管理
        </el-button>
        <el-button type="primary" plain @click="$router.push('/orgs')">
          组织管理
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
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.stat-scope {
  font-size: 12px;
  color: #c0c4cc;
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
  max-width: 700px;
}

.action-list {
  display: flex;
  gap: 12px;
}
</style>