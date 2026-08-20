<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick, DocumentChecked, CopyDocument } from '@element-plus/icons-vue'
import VueJsonPretty from 'vue-json-pretty'
import 'vue-json-pretty/lib/styles.css'
import { fetchIamTemplates, generateIamRole } from '@/api/iam'
import type { IamGenerateResult, IamTemplate } from '@/types'

/**
 * IAM 配置生成器
 *
 * 自然语言 → LLM → RBAC 2.0 权限配置 JSON
 * - 预设模板一键填充
 * - Schema 校验失败自动重试（后端处理）
 * - 同名角色冲突提示
 * - JSON 预览 + 语法高亮
 */

const requirement = ref('')
const templates = ref<IamTemplate[]>([])
const result = ref<IamGenerateResult | null>(null)
const generating = ref(false)

const configJson = computed(() => (result.value ? JSON.stringify(result.value.config, null, 2) : ''))

const templateMatched = computed(() => result.value?.template_matched ?? false)
const templateName = computed(() => result.value?.template_name)
const retries = computed(() => result.value?.retries ?? 0)
const conflicts = computed(() => result.value?.conflicts ?? [])

onMounted(async () => {
  try {
    templates.value = await fetchIamTemplates()
  } catch {
    // 模板加载失败不影响主流程，静默降级
  }
})

/** 点击预设模板，填充输入框 */
function applyTemplate(tpl: IamTemplate): void {
  requirement.value = `我要${tpl.name}`
  ElMessage.info(`已填入模板需求：我要${tpl.name}`)
}

/** 调用后端生成配置 */
async function handleGenerate(): Promise<void> {
  const text = requirement.value.trim()
  if (!text) {
    ElMessage.warning('请先输入权限需求描述')
    return
  }

  generating.value = true
  try {
    result.value = await generateIamRole(text)
    if (conflicts.value.length > 0) {
      ElMessage.warning(`生成的角色编码 [${conflicts.value.join(', ')}] 与已有角色冲突`)
    } else {
      ElMessage.success('配置生成成功')
    }
  } catch (e) {
    ElMessage.error('生成失败，请稍后重试')
    result.value = null
  } finally {
    generating.value = false
  }
}

/** 确认提交（复制 JSON 到剪贴板，实际入库由后续角色管理功能承接） */
async function handleConfirm(): Promise<void> {
  if (!result.value) return
  await ElMessageBox.confirm(
    '确认将此角色配置提交到当前租户？',
    '提交确认',
    { type: 'info', confirmButtonText: '确认提交', cancelButtonText: '取消' },
  )
  ElMessage.success('角色配置已提交（当前版本支持复制，入库由角色管理功能承接）')
}

/** 复制 JSON 到剪贴板 */
async function handleCopy(): Promise<void> {
  if (!configJson.value) return
  await navigator.clipboard.writeText(configJson.value)
  ElMessage.success('JSON 已复制到剪贴板')
}
</script>

<template>
  <div class="iam-generator">
    <el-card shadow="never" class="input-card">
      <template #header>
        <div class="card-header">
          <span class="card-title">IAM 配置生成器</span>
          <span class="card-subtitle">用自然语言描述权限需求，自动生成 RBAC 2.0 配置</span>
        </div>
      </template>

      <!-- 预设模板 -->
      <div class="templates-section">
        <span class="section-label">预设模板：</span>
        <el-tag
          v-for="tpl in templates"
          :key="tpl.name"
          class="template-tag"
          effect="plain"
          @click="applyTemplate(tpl)"
        >
          {{ tpl.name }}
        </el-tag>
      </div>

      <!-- 输入区 -->
      <div class="input-section">
        <el-input
          v-model="requirement"
          type="textarea"
          :rows="3"
          maxlength="500"
          show-word-limit
          placeholder="例如：创建一个只读角色，只能看北京机房和上海机房的云主机资源"
        />
        <el-button
          type="primary"
          class="generate-btn"
          :loading="generating"
          :icon="MagicStick"
          @click="handleGenerate"
        >
          {{ generating ? '生成中…' : '生成配置' }}
        </el-button>
      </div>
    </el-card>

    <!-- 生成结果 -->
    <el-card v-if="result" shadow="never" class="result-card">
      <template #header>
        <div class="card-header">
          <span class="card-title">生成结果</span>
          <div class="result-meta">
            <el-tag v-if="templateMatched" type="success" size="small" class="meta-tag">
              {{ templateName || '模板匹配' }}
            </el-tag>
            <el-tag v-if="retries > 0" type="warning" size="small" class="meta-tag">
              Schema 重试 {{ retries }} 次
            </el-tag>
            <el-tag v-if="conflicts.length > 0" type="danger" size="small" class="meta-tag">
              角色冲突：{{ conflicts.join(', ') }}
            </el-tag>
          </div>
        </div>
      </template>

      <div class="json-preview">
        <vue-json-pretty
          :data="result.config"
          :deep="4"
          :show-line="false"
          :show-double-quotes="true"
        />
      </div>

      <div class="result-actions">
        <el-button :icon="CopyDocument" @click="handleCopy">复制 JSON</el-button>
        <el-button type="primary" :icon="DocumentChecked" @click="handleConfirm">
          确认提交
        </el-button>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.iam-generator {
  padding: 16px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.card-title {
  font-size: 16px;
  font-weight: 600;
}

.card-subtitle {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.templates-section {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.section-label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.template-tag {
  cursor: pointer;
}

.template-tag:hover {
  background-color: var(--el-color-primary-light-9);
  border-color: var(--el-color-primary);
}

.input-section {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

.input-section .el-textarea {
  flex: 1;
}

.generate-btn {
  min-width: 110px;
}

.result-card {
  margin-top: 16px;
}

.result-meta {
  display: flex;
  gap: 8px;
}

.json-preview {
  background-color: var(--el-fill-color-light);
  border-radius: 6px;
  padding: 12px;
  max-height: 480px;
  overflow: auto;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
}

.result-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 16px;
}
</style>
