<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { UserFilled, Lock } from '@element-plus/icons-vue'
import type { FormInstance, FormRules } from 'element-plus'

/**
 * 登录页
 * 当前为纯前端占位版本，后续对接 FastAPI 认证后端
 */

const router = useRouter()
const formRef = ref<FormInstance>()
const loading = ref(false)

interface LoginForm {
  username: string
  password: string
}

const formData = reactive<LoginForm>({
  username: '',
  password: '',
})

const formRules: FormRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码长度不能少于 6 位', trigger: 'blur' },
  ],
}

async function handleLogin(): Promise<void> {
  if (!formRef.value) return

  try {
    await formRef.value.validate()
    loading.value = true

    // 模拟登录延迟（后续对接后端 API）
    await new Promise((resolve) => setTimeout(resolve, 800))

    // 简易鉴权：Mock 模式下任意用户名密码均可登录
    localStorage.setItem('token', 'mock-jwt-token')
    localStorage.setItem('username', formData.username)
    ElMessage.success('登录成功')
    router.push('/home')
  } catch {
    // 表单校验不通过
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <div class="login-card">
      <div class="login-header">
        <h1>Oasis Curator</h1>
        <p>绿洲馆长 · 认证授权基础设施</p>
      </div>
      <el-form
        ref="formRef"
        :model="formData"
        :rules="formRules"
        size="large"
        @keyup.enter="handleLogin"
      >
        <el-form-item prop="username">
          <el-input
            v-model="formData.username"
            placeholder="用户名"
            :prefix-icon="UserFilled"
          />
        </el-form-item>
        <el-form-item prop="password">
          <el-input
            v-model="formData.password"
            type="password"
            placeholder="密码"
            :prefix-icon="Lock"
            show-password
          />
        </el-form-item>
        <el-form-item>
          <el-button
            type="primary"
            :loading="loading"
            style="width: 100%"
            @click="handleLogin"
          >
            登 录
          </el-button>
        </el-form-item>
      </el-form>
      <div class="login-footer">
        <span>Mock 模式 — 任意用户名密码均可登录</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 100vh;
  background: linear-gradient(135deg, #1e3c72 0%, #2a5298 50%, #1e3c72 100%);
}

.login-card {
  width: 400px;
  padding: 40px 36px;
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
}

.login-header {
  text-align: center;
  margin-bottom: 32px;
}

.login-header h1 {
  margin: 0;
  font-size: 26px;
  font-weight: 700;
  color: #1e3c72;
  letter-spacing: 2px;
}

.login-header p {
  margin: 8px 0 0;
  font-size: 13px;
  color: #909399;
}

.login-footer {
  text-align: center;
  margin-top: 16px;
  font-size: 12px;
  color: #c0c4cc;
}
</style>