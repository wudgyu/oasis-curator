import { createRouter, createWebHashHistory } from 'vue-router'
import type { RouteRecordRaw, NavigationGuardNext, RouteLocationNormalized } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

/**
 * 路由配置
 * - /login：独立页面，无 Layout 包裹
 * - / (AppLayout)：主布局包裹的管理页面
 */

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Login.vue'),
    meta: { title: '登录', noAuth: true },
  },
  {
    path: '/',
    component: () => import('@/components/AppLayout.vue'),
    redirect: '/home',
    children: [
      {
        path: 'home',
        name: 'Home',
        component: () => import('@/views/Home.vue'),
        meta: { title: '首页' },
      },
      {
        path: 'users',
        name: 'UserManagement',
        component: () => import('@/views/UserManagement.vue'),
        meta: { title: '用户管理' },
      },
    ],
  },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

/**
 * 全局前置导航守卫
 * 使用 Pinia authStore 校验登录状态
 *
 * 类比：Spring Security FilterChainProxy
 * - noAuth meta → 放行（类似 permitAll）
 * - 无 token → 重定向 /login（类似 AuthenticationEntryPoint）
 */
router.beforeEach(
  (to: RouteLocationNormalized, _from: RouteLocationNormalized, next: NavigationGuardNext) => {
    // 在导航守卫中使用 Pinia store 需要在 app.use(pinia) 之后调用
    const authStore = useAuthStore()

    if (to.meta.noAuth) {
      // 已登录用户访问登录页 → 重定向到首页
      if (authStore.isLoggedIn) {
        next('/home')
        return
      }
      next()
      return
    }

    // 未登录 → 重定向到登录页
    if (!authStore.isLoggedIn) {
      next('/login')
      return
    }

    next()
  },
)

export default router