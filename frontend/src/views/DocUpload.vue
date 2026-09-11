<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete, UploadFilled } from '@element-plus/icons-vue'
import type { UploadRequestOptions } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { deleteDocument, fetchDocuments, uploadDocument } from '@/api/documents'
import type { ChunkStrategy, DocItem, DocVisibility, RoleCode } from '@/types'

/**
 * 文档上传与管理
 *
 * - 上传：拖拽文件到区域即按当前配置上传（解析 → 切分 → 向量化入库）
 * - 可见性：租户内公开 / 仅上传者可见 / 指定角色可见（后端强制过滤）
 * - 列表：按可见性过滤后分页返回，支持删除（仅上传者本人或 admin）
 */

const authStore = useAuthStore()

/** 能否上传/删除（后端同样校验，前端仅控制入口展示） */
const canWrite = computed(() => authStore.canWrite)

const uploadConfig = reactive({
  strategy: 'paragraphs' as ChunkStrategy,
  visibility: 'tenant' as DocVisibility,
  allowedRoles: [] as RoleCode[],
})

const visibilityOptions: Array<{ value: DocVisibility; label: string; tip: string }> = [
  { value: 'tenant', label: '租户内公开', tip: '本租户所有成员均可检索' },
  { value: 'private', label: '仅上传者可见', tip: '仅你自己可检索到该文档' },
  { value: 'roles', label: '指定角色可见', tip: '仅所选角色的成员可检索' },
]

const roleOptions: Array<{ value: RoleCode; label: string }> = [
  { value: 'manager', label: '经理' },
  { value: 'auditor', label: '审计员' },
  { value: 'employee', label: '员工' },
]

const strategyOptions: Array<{ value: ChunkStrategy; label: string }> = [
  { value: 'paragraphs', label: '按段落（推荐，500-800 字符）' },
  { value: 'chars', label: '按字符（固定 500，重叠 100）' },
]

// ---------- 上传 ----------
const uploading = ref(false)
const uploadPercent = ref(0)

/** 校验可见性配置，不合法时提示并返回 false */
function validateConfig(): boolean {
  if (uploadConfig.visibility === 'roles' && uploadConfig.allowedRoles.length === 0) {
    ElMessage.warning('可见性为「指定角色可见」时，请至少选择一个角色')
    return false
  }
  return true
}

/**
 * 自定义上传：替换 el-upload 默认的 XHR，
 * 走统一请求层（自动带 Token），并回传上传进度
 */
async function handleUpload(options: UploadRequestOptions): Promise<void> {
  if (!validateConfig()) {
    options.onError(new Error('可见性配置不合法') as never)
    return
  }
  uploading.value = true
  uploadPercent.value = 0
  try {
    const result = await uploadDocument(
      options.file as File,
      {
        strategy: uploadConfig.strategy,
        visibility: uploadConfig.visibility,
        allowedRoles: uploadConfig.allowedRoles,
      },
      (percent) => {
        uploadPercent.value = percent
      },
    )
    // 回传结果给 el-upload，保持其内部文件状态一致（列表隐藏，仅状态维护）
    options.onSuccess(result)
    const pages = result.pageCount ? `，${result.pageCount} 页` : ''
    ElMessage.success(
      `《${result.fileName}》解析完成${pages}，切分为 ${result.chunkCount} 个文本块，已入库`,
    )
    await loadDocuments()
  } catch (error) {
    options.onError(error as never)
    // 错误提示由 Axios 拦截器统一处理
  } finally {
    uploading.value = false
    uploadPercent.value = 0
  }
}

/** 上传前的类型/大小校验（后端同样校验） */
function beforeUpload(file: File): boolean {
  const allowed = ['.pdf', '.docx', '.txt', '.md', '.markdown']
  const ext = file.name.slice(file.name.lastIndexOf('.')).toLowerCase()
  if (!allowed.includes(ext)) {
    ElMessage.error(`不支持的格式 ${ext}，请上传 PDF / Word / TXT / Markdown`)
    return false
  }
  if (file.size > 50 * 1024 * 1024) {
    ElMessage.error('文件超过 50MB 限制')
    return false
  }
  return true
}

// ---------- 列表 ----------
const loading = ref(false)
const docs = ref<DocItem[]>([])
const pagination = reactive({ page: 1, pageSize: 10, total: 0 })

async function loadDocuments(): Promise<void> {
  loading.value = true
  try {
    const result = await fetchDocuments({ page: pagination.page, pageSize: pagination.pageSize })
    docs.value = result.items
    pagination.total = result.total
    // 删除后当前页可能为空，回退一页
    if (docs.value.length === 0 && pagination.page > 1) {
      pagination.page -= 1
      await loadDocuments()
    }
  } catch {
    // 错误提示由拦截器统一处理
  } finally {
    loading.value = false
  }
}

function handlePageChange(page: number): void {
  pagination.page = page
  loadDocuments()
}

/** 是否可删除：管理员或上传者本人（与后端规则一致） */
function canDelete(doc: DocItem): boolean {
  return canWrite.value && (doc.isOwner || authStore.isAdmin)
}

async function handleDelete(doc: DocItem): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `删除后该文档及其全部向量将从知识库中移除，且不可恢复。确定删除《${doc.fileName}》？`,
      '删除确认',
      { confirmButtonText: '确定删除', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  try {
    await deleteDocument(doc.id)
    ElMessage.success('文档已删除')
    await loadDocuments()
  } catch {
    // 错误提示由拦截器统一处理
  }
}

// ---------- 展示辅助 ----------
const typeLabels: Record<string, string> = {
  pdf: 'PDF',
  word: 'Word',
  markdown: 'Markdown',
  txt: '文本',
}

const visibilityLabels: Record<string, string> = {
  tenant: '租户内公开',
  private: '仅本人可见',
  roles: '指定角色',
}

const visibilityTags: Record<string, 'success' | 'warning' | 'primary'> = {
  tenant: 'success',
  private: 'warning',
  roles: 'primary',
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function formatTime(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

onMounted(loadDocuments)
</script>

<template>
  <div class="doc-upload">
    <!-- 上传区 -->
    <el-card v-if="canWrite" shadow="never" class="upload-card">
      <template #header>
        <span class="card-title">上传文档</span>
      </template>

      <el-form :inline="true" class="config-form">
        <el-form-item label="切分策略">
          <el-select v-model="uploadConfig.strategy" style="width: 240px">
            <el-option
              v-for="item in strategyOptions"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="可见性">
          <el-select v-model="uploadConfig.visibility" style="width: 180px">
            <el-option
              v-for="item in visibilityOptions"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item v-if="uploadConfig.visibility === 'roles'" label="可见角色">
          <el-select
            v-model="uploadConfig.allowedRoles"
            multiple
            collapse-tags
            placeholder="选择角色"
            style="width: 220px"
          >
            <el-option
              v-for="item in roleOptions"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <p class="config-tip">
        {{ visibilityOptions.find((o) => o.value === uploadConfig.visibility)?.tip }}；
        上传后自动完成解析、切分与向量化，可直接在「文档问答」中提问。
      </p>

      <el-upload
        drag
        :show-file-list="false"
        :http-request="handleUpload"
        :before-upload="beforeUpload"
        :disabled="uploading"
        accept=".pdf,.docx,.txt,.md,.markdown"
        class="upload-dragger"
      >
        <el-icon class="upload-icon"><UploadFilled /></el-icon>
        <div class="upload-text">将文件拖到此处，或<em>点击选择</em></div>
        <div class="upload-hint">支持 PDF / Word / TXT / Markdown，单文件不超过 50MB</div>
      </el-upload>

      <el-progress
        v-if="uploading"
        :percentage="uploadPercent"
        :stroke-width="12"
        striped
        class="upload-progress"
      />
    </el-card>

    <el-alert
      v-else
      type="info"
      show-icon
      :closable="false"
      title="当前角色为只读，可查看与检索文档但无法上传"
      class="readonly-alert"
    />

    <!-- 文档列表 -->
    <el-card shadow="never">
      <template #header>
        <div class="list-header">
          <span class="card-title">文档库</span>
          <el-button size="small" @click="loadDocuments">刷新</el-button>
        </div>
      </template>

      <el-table v-loading="loading" :data="docs" empty-text="暂无文档" style="width: 100%">
        <el-table-column prop="fileName" label="文件名" min-width="240" show-overflow-tooltip />
        <el-table-column label="类型" width="100">
          <template #default="{ row }">
            <el-tag size="small" type="info">{{ typeLabels[row.fileType] ?? row.fileType }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="大小" width="100">
          <template #default="{ row }">{{ formatSize(row.fileSize) }}</template>
        </el-table-column>
        <el-table-column prop="chunkCount" label="文本块" width="90" />
        <el-table-column label="可见性" width="140">
          <template #default="{ row }">
            <el-tag size="small" :type="visibilityTags[row.visibility] ?? 'info'">
              {{ visibilityLabels[row.visibility] ?? row.visibility }}
            </el-tag>
            <span v-if="row.visibility === 'roles'" class="roles-hint">
              {{ row.allowedRoles.length }} 个角色
            </span>
          </template>
        </el-table-column>
        <el-table-column label="上传时间" width="160">
          <template #default="{ row }">{{ formatTime(row.createdAt) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="canDelete(row as DocItem)"
              type="danger"
              size="small"
              text
              :icon="Delete"
              @click="handleDelete(row as DocItem)"
            >
              删除
            </el-button>
            <span v-else class="no-action">—</span>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        v-if="pagination.total > 0"
        class="pagination"
        layout="total, prev, pager, next"
        :total="pagination.total"
        :page-size="pagination.pageSize"
        :current-page="pagination.page"
        @current-change="handlePageChange"
      />
    </el-card>
  </div>
</template>

<style scoped>
.doc-upload {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.card-title {
  font-weight: 600;
  color: #303133;
}

.config-form {
  margin-bottom: 4px;
}

.config-tip {
  margin: 0 0 12px;
  font-size: 13px;
  color: #909399;
}

.readonly-alert {
  margin-bottom: 0;
}

.upload-dragger :deep(.el-upload-dragger) {
  padding: 28px 20px;
}

.upload-icon {
  font-size: 42px;
  color: #c0c4cc;
}

.upload-text {
  margin-top: 8px;
  font-size: 14px;
  color: #606266;
}

.upload-text em {
  color: #409eff;
  font-style: normal;
}

.upload-hint {
  margin-top: 6px;
  font-size: 12px;
  color: #909399;
}

.upload-progress {
  margin-top: 12px;
}

.list-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.roles-hint {
  margin-left: 6px;
  font-size: 12px;
  color: #909399;
}

.no-action {
  color: #c0c4cc;
}

.pagination {
  margin-top: 14px;
  justify-content: flex-end;
}
</style>
