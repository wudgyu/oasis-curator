import { createRouter, createWebHashHistory } from 'vue-router'
import type { RouteRecordRaw, NavigationGuardNext, RouteLocationNormalized } from 'vue-router'

/**
 * 路由配置
 * - 登录页（无 Layout，独立页面）
 * - 主布局（AppLayout）包裹的管理页面
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
 * 检查 token 是否存在，未登录用户重定向到登录页
 */
router.beforeEach(
  (to: RouteLocationNormalized, _from: RouteLocationNormalized, next: NavigationGuardNext) => {
    const token = localStorage.getItem('token')

    // 目标页面不需要认证（如登录页）
    if (to.meta.noAuth) {
      // 已登录用户访问登录页 → 重定向到首页
      if (token) {
        next('/home')
        return
      }
      next()
      return
    }

    // 未登录 → 重定向到登录页
    if (!token) {
      next('/login')
      return
    }

    next()
  },
)

export default router