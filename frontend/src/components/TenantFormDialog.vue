<script setup lang="ts">
import { ref, reactive, watch } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import type { TenantFormData } from '@/types'

/**
 * 租户表单对话框组件
 * 支持新增/编辑双模式
 */

// ---------- Props ----------
const props = defineProps<{
  /** 对话框是否可见 */
  visible: boolean
  /** 是否为编辑模式 */
  isEditing: boolean
  /** 表单初始数据（编辑时传入已有租户数据） */
  initialData?: TenantFormData
}>()

// ---------- Emits ----------
const emit = defineEmits<{
  /** 确认提交 */
  (e: 'confirm', data: TenantFormData): void
  /** 取消 */
  (e: 'cancel'): void
}>()

// ---------- 表单 ----------
const formRef = ref<FormInstance>()

const formData = reactive<TenantFormData>({
  name: '',
  plan: 'basic',
  status: 'active',
})

const formRules: FormRules = {
  name: [
    { required: true, message: '请输入租户名称', trigger: 'blur' },
    { min: 2, max: 30, message: '租户名称长度在 2 到 30 个字符', trigger: 'blur' },
  ],
  plan: [
    { required: true, message: '请选择套餐', trigger: 'change' },
  ],
}

// 监听对话框打开，回填初始数据
watch(
  () => props.visible,
  (newVal) => {
    if (newVal && props.initialData) {
      formData.name = props.initialData.name
      formData.plan = props.initialData.plan
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
    :title="isEditing ? '编辑租户' : '新增租户'"
    width="480px"
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
      <el-form-item label="租户名称" prop="name">
        <el-input
          v-model="formData.name"
          placeholder="请输入租户名称"
          maxlength="30"
          show-word-limit
        />
      </el-form-item>
      <el-form-item label="套餐" prop="plan">
        <el-select
          v-model="formData.plan"
          placeholder="请选择套餐"
          style="width: 100%"
        >
          <el-option label="基础版 (basic)" value="basic" />
          <el-option label="专业版 (pro)" value="pro" />
          <el-option label="企业版 (enterprise)" value="enterprise" />
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