<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { CircleCheck, CircleClose, Loading, MagicStick } from '@element-plus/icons-vue'
import { runAgentStream } from '@/api/agent'
import { fetchDocuments } from '@/api/documents'
import { useAuthStore } from '@/stores/auth'
import type { AgentStep, DocItem, DocVisibility, RoleCode } from '@/types'

/**
 * 文档处理 Agent
 *
 * 用户描述需求 → LLM 自主选择工具并编排执行顺序 → 实时展示每一步的
 * 工具调用、参数、耗时与结果，最后给出回复（非黑盒）。
 */

const authStore = useAuthStore()
const canRun = computed(() => authStore.canWrite)

// ---------- 表单 ----------
const form = reactive({
  docId: '' as string,
  instruction: '',
  visibility: 'tenant' as DocVisibility,
  allowedRoles: [] as RoleCode[],
  provider: '' as string,
  mode: 'auto',
})

const PRESET_TASKS = [
  { label: '解析并入库', text: '上传这份文档并入库' },
  { label: '提取表格', text: '这份文档有表格，提取出来' },
  { label: '生成摘要', text: '帮我总结这份文档的核心内容' },
  { label: '解析+摘要+入库', text: '把这份文档解析、摘要后入库' },
]

const visibilityOptions: Array<{ value: DocVisibility; label: string }> = [
  { value: 'tenant', label: '租户内公开' },
  { value: 'private', label: '仅本人可见' },
  { value: 'roles', label: '指定角色' },
]

const roleOptions: Array<{ value: RoleCode; label: string }> = [
  { value: 'manager', label: '经理' },
  { value: 'auditor', label: '审计员' },
  { value: 'employee', label: '员工' },
]

// ---------- 文档列表 ----------
const documents = ref<DocItem[]>([])
const docsLoading = ref(false)

async function loadDocuments(): Promise<void> {
  docsLoading.value = true
  try {
    const result = await fetchDocuments({ page: 1, pageSize: 100 })
    documents.value = result.items
    if (!form.docId && result.items.length > 0) {
      form.docId = result.items[0].id
    }
  } catch {
    // 错误提示由拦截器统一处理
  } finally {
    docsLoading.value = false
  }
}

// ---------- 执行 ----------
const running = ref(false)
const steps = ref<AgentStep[]>([])
const answer = ref('')
const runMeta = ref<{ provider: string; model: string; mode: string; iterations: number; finished: boolean } | null>(null)
let controller: AbortController | null = null

function applyPreset(text: string): void {
  form.instruction = text
}

function validate(): boolean {
  if (!form.instruction.trim()) {
    ElMessage.warning('请先描述处理需求')
    return false
  }
  if (!form.docId) {
    ElMessage.warning('请选择要处理的文档')
    return false
  }
  if (form.visibility === 'roles' && form.allowedRoles.length === 0) {
    ElMessage.warning('可见性为「指定角色」时请至少选择一个角色')
    return false
  }
  return true
}

async function run(): Promise<void> {
  if (!validate()) return
  running.value = true
  steps.value = []
  answer.value = ''
  runMeta.value = null
  controller = new AbortController()

  try {
    await runAgentStream(
      {
        instruction: form.instruction.trim(),
        docId: form.docId,
        visibility: form.visibility,
        allowedRoles: form.allowedRoles,
        provider: form.provider || null,
        mode: form.mode,
      },
      {
        onStep: (step) => {
          steps.value.push(step)
        },
        onDone: (result) => {
          answer.value = result.answer
          runMeta.value = {
            provider: result.provider,
            model: result.model,
            mode: result.mode,
            iterations: result.iterations,
            finished: result.finished,
          }
          // 用最终轨迹覆盖（流式 step 与 done 中一致，此处保证完整性）
          steps.value = result.steps
          void loadDocuments()
        },
        onError: (message) => {
          ElMessage.error(message)
        },
      },
      controller.signal,
    )
  } catch (error) {
    if ((error as Error).name !== 'AbortError') {
      ElMessage.error((error as Error).message || '执行失败')
    }
  } finally {
    running.value = false
    controller = null
  }
}

function stop(): void {
  controller?.abort()
  running.value = false
  ElMessage.info('已中断执行')
}

/** 工具结果格式化展示 */
function prettyResult(step: AgentStep): string {
  return JSON.stringify(step.result, null, 2)
}

function argsText(step: AgentStep): string {
  const entries = Object.entries(step.args).filter(([k]) => k !== '__raw__')
  if (entries.length === 0) return '（无参数）'
  return entries.map(([k, v]) => `${k}=${JSON.stringify(v)}`).join('，')
}

onMounted(loadDocuments)
onBeforeUnmount(() => controller?.abort())
</script>

<template>
  <div class="doc-agent">
    <el-alert
      v-if="!canRun"
      type="info"
      show-icon
      :closable="false"
      title="仅管理员和经理角色可执行文档处理 Agent"
      class="readonly-alert"
    />

    <!-- 需求配置 -->
    <el-card shadow="never">
      <template #header>
        <span class="card-title">处理需求</span>
      </template>

      <el-form label-width="90px" :disabled="!canRun">
        <el-form-item label="目标文档">
          <el-select
            v-model="form.docId"
            filterable
            placeholder="选择要处理的文档"
            :loading="docsLoading"
            style="width: 100%; max-width: 520px"
          >
            <el-option
              v-for="doc in documents"
              :key="doc.id"
              :label="`${doc.fileName}（${doc.fileType}，${doc.chunkCount} 块）`"
              :value="doc.id"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="处理需求">
          <el-input
            v-model="form.instruction"
            type="textarea"
            :rows="2"
            placeholder="用自然语言描述要做什么，例如：把这份文档解析、摘要后入库"
          />
          <div class="presets">
            <el-button
              v-for="preset in PRESET_TASKS"
              :key="preset.label"
              size="small"
              @click="applyPreset(preset.text)"
            >
              {{ preset.label }}
            </el-button>
          </div>
        </el-form-item>

        <el-form-item label="入库可见性">
          <el-select v-model="form.visibility" style="width: 160px">
            <el-option
              v-for="item in visibilityOptions"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
          <el-select
            v-if="form.visibility === 'roles'"
            v-model="form.allowedRoles"
            multiple
            collapse-tags
            placeholder="选择角色"
            style="width: 220px; margin-left: 10px"
          >
            <el-option
              v-for="item in roleOptions"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="模型与模式">
          <el-select v-model="form.provider" style="width: 160px">
            <el-option label="默认（自动降级）" value="" />
            <el-option label="DeepSeek" value="deepseek" />
            <el-option label="Kimi" value="kimi" />
          </el-select>
          <el-select v-model="form.mode" style="width: 220px; margin-left: 10px">
            <el-option label="auto（原生优先，失败降级）" value="auto" />
            <el-option label="native（原生 Function Calling）" value="native" />
            <el-option label="prompt（Prompt 注入）" value="prompt" />
          </el-select>
        </el-form-item>

        <el-form-item>
          <el-button
            type="primary"
            :icon="MagicStick"
            :loading="running"
            :disabled="!canRun"
            @click="run"
          >
            执行
          </el-button>
          <el-button v-if="running" @click="stop">中断</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 执行过程 -->
    <el-card v-if="running || steps.length || answer" shadow="never" class="trace-card">
      <template #header>
        <div class="trace-header">
          <span class="card-title">执行过程</span>
          <span v-if="running" class="running-tip">
            <el-icon class="is-loading"><Loading /></el-icon> Agent 执行中…
          </span>
          <span v-else-if="runMeta" class="meta-tip">
            {{ runMeta.provider }}/{{ runMeta.model }} · {{ runMeta.mode }} 模式 ·
            {{ runMeta.iterations }} 轮 · {{ runMeta.finished ? '已收敛' : '未收敛' }}
          </span>
        </div>
      </template>

      <el-empty v-if="!steps.length && running" description="正在分析需求…" />

      <div v-for="step in steps" :key="step.index" class="step">
        <div class="step-head">
          <el-icon v-if="step.ok" class="ok"><CircleCheck /></el-icon>
          <el-icon v-else class="fail"><CircleClose /></el-icon>
          <span class="step-index">{{ step.index }}</span>
          <span class="step-tool">{{ step.tool }}</span>
          <span class="step-args">{{ argsText(step) }}</span>
          <span class="step-time">{{ step.elapsedMs }}ms</span>
        </div>
        <div v-if="step.error" class="step-error">错误：{{ step.error }}</div>
        <el-collapse class="step-detail">
          <el-collapse-item :title="step.ok ? '查看结果' : '查看详情'">
            <pre class="result-pre">{{ prettyResult(step) }}</pre>
          </el-collapse-item>
        </el-collapse>
      </div>
    </el-card>

    <!-- 最终答复 -->
    <el-card v-if="answer" shadow="never">
      <template #header>
        <span class="card-title">最终答复</span>
      </template>
      <div class="answer">{{ answer }}</div>
    </el-card>
  </div>
</template>

<style scoped>
.doc-agent {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.card-title {
  font-weight: 600;
  color: #303133;
}

.readonly-alert {
  margin-bottom: 0;
}

.presets {
  margin-top: 8px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.trace-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.running-tip {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #409eff;
}

.meta-tip {
  font-size: 12px;
  color: #909399;
}

.step {
  border-left: 3px solid #409eff;
  background: #f7f8fa;
  border-radius: 4px;
  padding: 10px 12px;
  margin-bottom: 10px;
}

.step-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.ok {
  color: #67c23a;
}

.fail {
  color: #f56c6c;
}

.step-index {
  font-weight: 600;
  color: #909399;
}

.step-tool {
  font-weight: 600;
  color: #303133;
}

.step-args {
  font-size: 12px;
  color: #606266;
  word-break: break-all;
}

.step-time {
  margin-left: auto;
  font-size: 12px;
  color: #909399;
}

.step-error {
  margin-top: 6px;
  font-size: 13px;
  color: #f56c6c;
}

.step-detail {
  margin-top: 6px;
}

.result-pre {
  margin: 0;
  font-size: 12px;
  line-height: 1.6;
  color: #303133;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 260px;
  overflow: auto;
}

.answer {
  font-size: 14px;
  line-height: 1.8;
  color: #303133;
  white-space: pre-wrap;
}
</style>
