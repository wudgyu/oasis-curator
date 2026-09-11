<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ChatDotRound, Delete, Plus, Promotion } from '@element-plus/icons-vue'
import {
  askStream,
  deleteConversation,
  fetchConversationDetail,
  fetchConversations,
} from '@/api/qa'
import type { ChatMessageItem, ConversationItem, MessageSource } from '@/types'

/**
 * 文档问答（RAG 对话）
 *
 * - 左侧会话列表：新建 / 切换 / 删除，切换后上下文独立
 * - 右侧聊天窗口：SSE 流式逐字输出，回答中的 [来源: 文件名, 第N段] 可点击查看原文
 * - 拒答：文档库无相关内容时展示明确提示而非编造
 */

/** 引用标注匹配：与后端 rag_pipeline.CITATION_RE 保持一致（兼容全角标点与空格） */
const CITATION_RE = /\[来源[:：]\s*([^,，\]]+?)\s*[,，]\s*第\s*(\d+)\s*段\]/g

const conversations = ref<ConversationItem[]>([])
const currentConversationId = ref<string | null>(null)
const messages = ref<ChatMessageItem[]>([])
const question = ref('')
const streaming = ref(false)
const loadingDetail = ref(false)
const listLoading = ref(false)

const messagesEl = ref<HTMLElement | null>(null)
let abortController: AbortController | null = null

// ---------- 引用原文抽屉 ----------
const sourceDrawer = ref(false)
const activeSource = ref<{ source: MessageSource; label: string } | null>(null)

// ---------- 会话列表 ----------
async function loadConversations(): Promise<void> {
  listLoading.value = true
  try {
    conversations.value = await fetchConversations()
  } catch {
    // 错误提示由拦截器统一处理
  } finally {
    listLoading.value = false
  }
}

async function selectConversation(id: string): Promise<void> {
  if (streaming.value || id === currentConversationId.value) return
  currentConversationId.value = id
  loadingDetail.value = true
  try {
    const detail = await fetchConversationDetail(id)
    messages.value = detail.messages
    await scrollToBottom()
  } catch {
    // 错误提示由拦截器统一处理
  } finally {
    loadingDetail.value = false
  }
}

function startNewConversation(): void {
  if (streaming.value) return
  currentConversationId.value = null
  messages.value = []
  question.value = ''
}

async function handleDeleteConversation(item: ConversationItem, event: Event): Promise<void> {
  event.stopPropagation()
  if (streaming.value) return
  try {
    await ElMessageBox.confirm(
      `删除会话「${item.title}」及其全部消息？`,
      '删除确认',
      { confirmButtonText: '确定删除', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  try {
    await deleteConversation(item.id)
    if (currentConversationId.value === item.id) startNewConversation()
    await loadConversations()
    ElMessage.success('会话已删除')
  } catch {
    // 错误提示由拦截器统一处理
  }
}

// ---------- 提问与流式接收 ----------
async function send(): Promise<void> {
  const text = question.value.trim()
  if (!text || streaming.value) return

  question.value = ''
  streaming.value = true
  abortController = new AbortController()

  // 本地先落用户消息与待生成的助手消息（后端并行落库）
  appendLocal('user', text)
  const assistant = appendLocal('assistant', '')
  await scrollToBottom()

  try {
    await askStream(
      { question: text, conversationId: currentConversationId.value },
      {
        onMeta: ({ conversationId, sources }) => {
          // 新会话由后端创建，回填 ID 并刷新列表（标题取首个问题）
          if (!currentConversationId.value) {
            currentConversationId.value = conversationId
            void loadConversations()
          }
          // 主回答消息与历史消息共用 sources，供点击引用展示原文
          assistant.sources = sources
        },
        onToken: (chunk) => {
          assistant.content += chunk
          void scrollToBottom()
        },
        onDone: ({ answer, refused, citations }) => {
          assistant.content = answer || assistant.content
          assistant.refused = refused
          assistant.citations = citations
          void loadConversations()
        },
        onError: (message) => {
          ElMessage.error(message)
          assistant.content = assistant.content || '（生成失败）'
        },
      },
      abortController.signal,
    )
  } catch (error) {
    if ((error as Error).name !== 'AbortError') {
      ElMessage.error((error as Error).message || '请求失败')
      assistant.content = assistant.content || '（请求失败）'
    } else if (!assistant.content) {
      assistant.content = '（已停止）'
    }
  } finally {
    streaming.value = false
    abortController = null
    // 会话标题/消息数可能已变化，刷新列表但保留当前消息
    void loadConversations()
    await scrollToBottom()
  }
}

function appendLocal(role: 'user' | 'assistant', content: string): ChatMessageItem {
  const item: ChatMessageItem = {
    id: `local-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    role,
    content,
    refused: false,
    citations: [],
    sources: [],
    createdAt: new Date().toISOString(),
  }
  messages.value.push(item)
  return item
}

function stopStreaming(): void {
  abortController?.abort()
  streaming.value = false
}

/** Enter 发送，Shift+Enter 换行 */
function handleKeydown(event: Event | KeyboardEvent): void {
  if (!(event instanceof KeyboardEvent)) return
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    void send()
  }
}

async function scrollToBottom(): Promise<void> {
  await nextTick()
  const el = messagesEl.value
  if (el) el.scrollTop = el.scrollHeight
}

// ---------- 引用与渲染 ----------
interface Segment {
  type: 'text' | 'cite'
  text: string
  key?: string
}

/** 把回答拆成普通文本与可点击的引用标注 */
function renderSegments(content: string): Segment[] {
  const segments: Segment[] = []
  let lastIndex = 0
  for (const match of content.matchAll(CITATION_RE)) {
    const index = match.index ?? 0
    if (index > lastIndex) {
      segments.push({ type: 'text', text: content.slice(lastIndex, index) })
    }
    segments.push({
      type: 'cite',
      text: match[0],
      key: `${match[1].trim()}, 第${match[2]}段`,
    })
    lastIndex = index + match[0].length
  }
  if (lastIndex < content.length) {
    segments.push({ type: 'text', text: content.slice(lastIndex) })
  }
  return segments
}

/** 点击引用：从该消息的候选块中定位原文 */
function openSource(message: ChatMessageItem, citationKey: string): void {
  const source = message.sources.find(
    (s) => `${s.sourceFile}, 第${s.chunkIndex + 1}段` === citationKey,
  )
  if (!source) {
    ElMessage.info('该引用的原文片段已不在本次检索结果中')
    return
  }
  activeSource.value = { source, label: citationKey }
  sourceDrawer.value = true
}

const currentTitle = computed(() => {
  const found = conversations.value.find((c) => c.id === currentConversationId.value)
  return found?.title ?? (messages.value.length ? '新会话' : '文档问答')
})

onMounted(async () => {
  await loadConversations()
  if (conversations.value.length > 0) {
    await selectConversation(conversations.value[0].id)
  }
})

onBeforeUnmount(() => {
  abortController?.abort()
})
</script>

<template>
  <div class="doc-qa">
    <!-- 会话列表 -->
    <aside class="conversation-pane">
      <el-button type="primary" :icon="Plus" class="new-btn" @click="startNewConversation">
        新建会话
      </el-button>
      <el-scrollbar class="conversation-list">
        <div v-if="!conversations.length && !listLoading" class="empty-tip">暂无历史会话</div>
        <div
          v-for="item in conversations"
          :key="item.id"
          class="conversation-item"
          :class="{ active: item.id === currentConversationId }"
          @click="selectConversation(item.id)"
        >
          <el-icon class="conv-icon"><ChatDotRound /></el-icon>
          <div class="conv-main">
            <div class="conv-title">{{ item.title }}</div>
            <div class="conv-meta">{{ item.messageCount }} 条消息</div>
          </div>
          <el-icon class="conv-delete" @click="handleDeleteConversation(item, $event)">
            <Delete />
          </el-icon>
        </div>
      </el-scrollbar>
    </aside>

    <!-- 聊天窗口 -->
    <section class="chat-pane">
      <header class="chat-header">
        <span class="chat-title">{{ currentTitle }}</span>
        <el-tag v-if="streaming" size="small" type="primary">生成中…</el-tag>
      </header>

      <div ref="messagesEl" v-loading="loadingDetail" class="messages">
        <el-empty
          v-if="!messages.length"
          description="向文档库提问，回答会标注来源并可点击查看原文"
        />
        <div
          v-for="message in messages"
          :key="message.id"
          class="message"
          :class="message.role"
        >
          <div class="bubble" :class="{ refused: message.refused }">
            <template v-if="message.role === 'assistant'">
              <template v-if="message.content">
                <template v-for="(seg, i) in renderSegments(message.content)" :key="i">
                  <span v-if="seg.type === 'text'">{{ seg.text }}</span>
                  <el-tag
                    v-else
                    size="small"
                    class="cite-tag"
                    @click="openSource(message, seg.key as string)"
                  >
                    {{ seg.text }}
                  </el-tag>
                </template>
              </template>
              <span v-else class="pending">思考中…</span>
            </template>
            <template v-else>{{ message.content }}</template>
          </div>
          <div v-if="message.refused" class="refused-hint">
            文档库中未找到相关内容，已明确拒答而非编造
          </div>
        </div>
      </div>

      <footer class="composer">
        <el-input
          v-model="question"
          type="textarea"
          :rows="2"
          resize="none"
          placeholder="输入问题，Enter 发送，Shift+Enter 换行"
          :disabled="streaming"
          @keydown="handleKeydown"
        />
        <div class="composer-actions">
          <el-button v-if="streaming" @click="stopStreaming">停止</el-button>
          <el-button
            type="primary"
            :icon="Promotion"
            :loading="streaming"
            :disabled="!question.trim()"
            @click="send"
          >
            发送
          </el-button>
        </div>
      </footer>
    </section>

    <!-- 引用原文 -->
    <el-drawer v-model="sourceDrawer" title="引用原文" size="440px">
      <template v-if="activeSource">
        <div class="source-meta">
          <el-tag size="small">{{ activeSource.source.sourceFile }}</el-tag>
          <el-tag size="small" type="info">第 {{ activeSource.source.chunkIndex + 1 }} 段</el-tag>
          <el-tag v-if="activeSource.source.page" size="small" type="info">
            第 {{ activeSource.source.page }} 页
          </el-tag>
          <el-tag size="small" type="success">相关度 {{ activeSource.source.score }}/10</el-tag>
        </div>
        <p class="source-label">{{ activeSource.label }}</p>
        <div class="source-text">{{ activeSource.source.text }}</div>
      </template>
    </el-drawer>
  </div>
</template>

<style scoped>
.doc-qa {
  display: flex;
  height: calc(100vh - 56px);
  background: #fff;
}

/* 会话列表 */
.conversation-pane {
  width: 260px;
  border-right: 1px solid #e6e6e6;
  display: flex;
  flex-direction: column;
  padding: 12px;
  gap: 10px;
}

.new-btn {
  width: 100%;
}

.conversation-list {
  flex: 1;
}

.empty-tip {
  padding: 12px 4px;
  font-size: 13px;
  color: #909399;
}

.conversation-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 6px;
  cursor: pointer;
  margin-bottom: 4px;
}

.conversation-item:hover {
  background: #f5f7fa;
}

.conversation-item.active {
  background: #ecf5ff;
}

.conv-icon {
  color: #909399;
}

.conv-main {
  flex: 1;
  min-width: 0;
}

.conv-title {
  font-size: 13px;
  color: #303133;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.conv-meta {
  font-size: 12px;
  color: #909399;
}

.conv-delete {
  color: #c0c4cc;
}

.conv-delete:hover {
  color: #f56c6c;
}

/* 聊天区 */
.chat-pane {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.chat-header {
  height: 48px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 16px;
  border-bottom: 1px solid #e6e6e6;
}

.chat-title {
  font-weight: 600;
  color: #303133;
}

.messages {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  background: #f7f8fa;
}

.message {
  display: flex;
  flex-direction: column;
  margin-bottom: 14px;
}

.message.user {
  align-items: flex-end;
}

.message.assistant {
  align-items: flex-start;
}

.bubble {
  max-width: 78%;
  padding: 10px 14px;
  border-radius: 8px;
  font-size: 14px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}

.message.user .bubble {
  background: #409eff;
  color: #fff;
}

.message.assistant .bubble {
  background: #fff;
  color: #303133;
  border: 1px solid #e6e6e6;
}

.message.assistant .bubble.refused {
  border-color: #f3d19e;
  background: #fdf6ec;
}

.pending {
  color: #909399;
}

.cite-tag {
  margin: 0 2px;
  cursor: pointer;
  vertical-align: baseline;
}

.cite-tag:hover {
  background: #d9ecff;
}

.refused-hint {
  margin-top: 4px;
  font-size: 12px;
  color: #e6a23c;
}

/* 输入区 */
.composer {
  border-top: 1px solid #e6e6e6;
  padding: 12px 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.composer-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

/* 引用抽屉 */
.source-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 10px;
}

.source-label {
  font-size: 12px;
  color: #909399;
  margin: 0 0 6px;
}

.source-text {
  font-size: 13px;
  line-height: 1.8;
  color: #303133;
  background: #f7f8fa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  padding: 12px;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
