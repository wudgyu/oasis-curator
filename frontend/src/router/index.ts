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
        path: 'tenants',
        name: 'TenantManagement',
        component: () => import('@/views/TenantManagement.vue'),
        meta: { title: '租户管理', requiresAdmin: true },
      },
      {
        path: 'orgs',
        name: 'OrgManagement',
        component: () => import('@/views/OrgManagement.vue'),
        meta: { title: '组织管理' },
      },
      {
        path: 'users',
        name: 'UserManagement',
        component: () => import('@/views/UserManagement.vue'),
        meta: { title: '用户管理' },
      },
      {
        path: 'documents',
        name: 'DocUpload',
        component: () => import('@/views/DocUpload.vue'),
        meta: { title: '文档管理' },
      },
      {
        path: 'qa',
        name: 'DocQA',
        component: () => import('@/views/DocQA.vue'),
        meta: { title: '文档问答' },
      },
      {
        path: 'iam-config',
        name: 'IamConfigGenerator',
        component: () => import('@/views/IamConfigGenerator.vue'),
        meta: { title: 'IAM 配置生成', requiresAdmin: true },
      },
      {
        path: 'roles',
        name: 'RoleManagement',
        component: () => import('@/views/RoleManagement.vue'),
        meta: { title: '角色管理', requiresAdmin: true },
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

    // 角色权限校验：requiresAdmin 路由仅 admin 可访问
    if (to.meta.requiresAdmin && !authStore.isAdmin) {
      next('/home')
      return
    }

    next()
  },
)

export default router