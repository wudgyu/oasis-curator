import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import router from './router'
import { useAuthStore } from '@/stores/auth'

const app = createApp(App)

app.use(createPinia())
app.use(router)

// 刷新页面后恢复会话：localStorage 中有 token 时，重新拉取用户信息
// （角色、租户上下文以服务端为准，防止本地缓存过期）
const authStore = useAuthStore()
if (authStore.isLoggedIn) {
  authStore.refreshUserInfo()
}

app.mount('#app')