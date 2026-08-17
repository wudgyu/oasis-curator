<script setup lang="ts">
import { ref, reactive, watch, computed } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import type { UserFormData } from '@/types'

/**
 * 用户表单对话框组件
 * 展示 defineProps<T>() 和 defineEmits<T>() 的泛型用法，
 * 以及 watch 监听 props 变化以回填表单数据
 *
 * 新增时密码必填；编辑时密码留空表示不修改。
 * 租户由后端根据当前登录用户自动归属，无需选择。
 */

// ---------- Props ----------
const props = defineProps<{
  /** 对话框是否可见 */
  visible: boolean
  /** 是否为编辑模式 */
  isEditing: boolean
  /** 表单初始数据（编辑时传入已有用户数据） */
  initialData?: UserFormData
}>()

// ---------- Emits ----------
const emit = defineEmits<{
  /** 确认提交 */
  (e: 'confirm', data: UserFormData): void
  /** 取消 */
  (e: 'cancel'): void
}>()

// ---------- 表单 ----------
const formRef = ref<FormInstance>()

const formData = reactive<UserFormData>({
  username: '',
  email: '',
  password: '',
  role: 'viewer',
  status: 'active',
})

const formRules = computed<FormRules>(() => ({
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 2, max: 20, message: '用户名长度在 2 到 20 个字符', trigger: 'blur' },
  ],
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { type: 'email', message: '请输入正确的邮箱格式', trigger: 'blur' },
  ],
  password: props.isEditing
    ? [{ min: 6, max: 128, message: '密码长度在 6 到 128 个字符（留空不修改）', trigger: 'blur' }]
    : [
        { required: true, message: '请输入密码', trigger: 'blur' },
        { min: 6, max: 128, message: '密码长度在 6 到 128 个字符', trigger: 'blur' },
      ],
  role: [
    { required: true, message: '请选择角色', trigger: 'change' },
  ],
}))

// 监听对话框打开，回填初始数据
watch(
  () => props.visible,
  (newVal) => {
    if (newVal && props.initialData) {
      formData.username = props.initialData.username
      formData.email = props.initialData.email
      formData.password = ''
      formData.role = props.initialData.role
      formData.status = props.initialData.status
    }
  },
)

// 关闭后重置表单
function handleClosed(): void {
  formRef.value?.resetFields()
}

async function handleSubmit(): Promise<void> {
  if (!formRef.value) return

  try {
    await formRef.value.validate()
    emit('confirm', { ...formData })
  } catch {
    // 表单校验不通过
  }
}
</script>

<template>
  <el-dialog
    :model-value="visible"
    :title="isEditing ? '编辑用户' : '新增用户'"
    width="520px"
    :close-on-click-modal="false"
    @closed="handleClosed"
    @update:model-value="(val: boolean) => !val && emit('cancel')"
  >
    <el-form
      ref="formRef"
      :model="formData"
      :rules="formRules"
      label-width="90px"
      status-icon
    >
      <el-form-item label="用户名" prop="username">
        <el-input
          v-model="formData.username"
          placeholder="请输入用户名"
          maxlength="20"
          show-word-limit
        />
      </el-form-item>
      <el-form-item label="邮箱" prop="email">
        <el-input
          v-model="formData.email"
          placeholder="请输入邮箱地址"
        />
      </el-form-item>
      <el-form-item label="密码" prop="password">
        <el-input
          v-model="formData.password"
          type="password"
          :placeholder="isEditing ? '留空表示不修改密码' : '请输入密码（至少 6 位）'"
          show-password
        />
      </el-form-item>
      <el-form-item label="角色" prop="role">
        <el-select
          v-model="formData.role"
          placeholder="请选择角色"
          style="width: 100%"
        >
          <el-option label="管理员 (admin)" value="admin" />
          <el-option label="编辑者 (editor)" value="editor" />
          <el-option label="观察者 (viewer)" value="viewer" />
        </el-select>
      </el-form-item>
      <el-form-item label="状态">
        <el-radio-group v-model="formData.status">
          <el-radio value="active">启用</el-radio>
          <el-radio value="disabled">禁用</el-radio>
        </el-radio-group>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="emit('cancel')">取消</el-button>
      <el-button type="primary" @click="handleSubmit">确定</el-button>
    </template>
  </el-dialog>
</template>