<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { Plus, Edit, Delete, Rank } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { fetchOrgTree, createOrg, renameOrg, moveOrg, deleteOrg } from '@/api/orgs'
import { fetchUsers } from '@/api/users'
import type { OrgTreeNode, User } from '@/types'

/**
 * 组织管理页面（对接 FastAPI 后端）
 * - 左侧组织树 + 节点操作；右侧选中组织的直属用户列表
 * - 写权限：admin 全树 / manager 限本组织子树内节点
 * - employee / auditor 只读
 */

const authStore = useAuthStore()

// ---------- 组织树 ----------
const tree = ref<OrgTreeNode[]>([])
const treeLoading = ref(false)
const selectedOrg = ref<OrgTreeNode | null>(null)

async function loadTree(): Promise<void> {
  treeLoading.value = true
  try {
    tree.value = await fetchOrgTree()
    // 默认选中当前用户所属组织
    if (!selectedOrg.value && authStore.orgId) {
      selectedOrg.value = findNode(tree.value, authStore.orgId) ?? null
    }
  } catch {
    // 错误提示由拦截器统一处理
  } finally {
    treeLoading.value = false
  }
}

function findNode(nodes: OrgTreeNode[], id: string): OrgTreeNode | null {
  for (const n of nodes) {
    if (n.id === id) return n
    const r = findNode(n.children, id)
    if (r) return r
  }
  return null
}

/** 节点是否可操作：admin 全部；manager 仅其子树内节点 */
function canOperate(node: OrgTreeNode): boolean {
  if (authStore.isAdmin) return true
  if (authStore.roleCode === 'manager') {
    return node.path.startsWith(authStore.orgPath)
  }
  return false
}

// ---------- 节点操作 ----------
async function handleAddChild(parent: OrgTreeNode): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt(
      `在「${parent.name}」下创建子组织`,
      '新增组织',
      {
        confirmButtonText: '创建',
        cancelButtonText: '取消',
        inputPattern: /^.{1,100}$/,
        inputErrorMessage: '名称长度 1-100 个字符',
      },
    )
    await createOrg(value, parent.id)
    ElMessage.success('组织创建成功')
    await loadTree()
  } catch {
    // 用户取消
  }
}

async function handleRename(node: OrgTreeNode): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt(
      `重命名「${node.name}」`,
      '重命名组织',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputValue: node.name,
        inputPattern: /^.{1,100}$/,
        inputErrorMessage: '名称长度 1-100 个字符',
      },
    )
    await renameOrg(node.id, value)
    ElMessage.success('重命名成功')
    await loadTree()
  } catch {
    // 用户取消
  }
}

const moveDialogVisible = ref(false)
const movingOrg = ref<OrgTreeNode | null>(null)
const moveTargetParentId = ref('')

/** 移动目标候选：排除自身及其子树 */
const moveTargetOptions = computed(() => {
  if (!movingOrg.value) return []
  const result: { id: string; name: string; disabled: boolean }[] = []
  function walk(nodes: OrgTreeNode[], depth: number): void {
    for (const n of nodes) {
      const disabled = Boolean(
        n.id === movingOrg.value!.id ||
        n.path.startsWith(movingOrg.value!.path) ||
        (movingOrg.value!.parentId && n.id === movingOrg.value!.parentId),
      )
      result.push({ id: n.id, name: '　'.repeat(depth) + n.name, disabled })
      walk(n.children, depth + 1)
    }
  }
  walk(tree.value, 0)
  return result
})

function openMoveDialog(node: OrgTreeNode): void {
  movingOrg.value = node
  moveTargetParentId.value = ''
  moveDialogVisible.value = true
}

async function handleMoveConfirm(): Promise<void> {
  if (!movingOrg.value || !moveTargetParentId.value) {
    ElMessage.warning('请选择目标父组织')
    return
  }
  try {
    await moveOrg(movingOrg.value.id, moveTargetParentId.value)
    ElMessage.success('组织移动成功')
    moveDialogVisible.value = false
    await loadTree()
  } catch {
    // 错误提示由拦截器统一处理
  }
}

async function handleDelete(node: OrgTreeNode): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `确定要删除组织「${node.name}」吗？仅空组织（无用户且无子组织）可删除。`,
      '删除确认',
      {
        confirmButtonText: '确定删除',
        cancelButtonText: '取消',
        type: 'warning',
      },
    )
    await deleteOrg(node.id)
    ElMessage.success(`已删除组织「${node.name}」`)
    await loadTree()
  } catch {
    // 用户取消或删除失败
  }
}

// ---------- 组织直属用户 ----------
const orgUsers = ref<User[]>([])
const orgUsersLoading = ref(false)

async function loadOrgUsers(): Promise<void> {
  if (!selectedOrg.value) {
    orgUsers.value = []
    return
  }
  orgUsersLoading.value = true
  try {
    const result = await fetchUsers({ page: 1, pageSize: 50, orgId: selectedOrg.value.id })
    orgUsers.value = result.items
  } catch {
    // 错误提示由拦截器统一处理
  } finally {
    orgUsersLoading.value = false
  }
}

function handleNodeClick(node: OrgTreeNode): void {
  selectedOrg.value = node
  loadOrgUsers()
}

const roleLabelMap: Record<string, string> = {
  manager: '经理',
  auditor: '审计员',
  employee: '员工',
}

// ---------- 初始化 ----------
onMounted(loadTree)
</script>

<template>
  <div class="org-management">
    <div class="page-header">
      <h1>组织管理</h1>
    </div>

    <div class="org-layout">
      <!-- 左侧：组织树 -->
      <el-card class="org-tree-card" shadow="never" v-loading="treeLoading">
        <template #header>
          <span>组织树</span>
        </template>
        <el-tree
          :data="tree"
          node-key="id"
          :props="{ label: 'name', children: 'children' }"
          highlight-current
          default-expand-all
          :expand-on-click-node="false"
          @node-click="handleNodeClick"
        >
          <template #default="{ data }">
            <div class="tree-node">
              <span class="node-label">
                {{ data.name }}
                <el-tag v-if="data.userCount > 0" size="small" type="info">
                  {{ data.userCount }}人
                </el-tag>
              </span>
              <span v-if="canOperate(data)" class="node-actions">
                <el-button
                  :icon="Plus"
                  link
                  size="small"
                  title="新增子组织"
                  @click.stop="handleAddChild(data)"
                />
                <el-button
                  :icon="Edit"
                  link
                  size="small"
                  title="重命名"
                  @click.stop="handleRename(data)"
                />
                <el-button
                  :icon="Rank"
                  link
                  size="small"
                  title="移动"
                  @click.stop="openMoveDialog(data)"
                />
                <el-button
                  :icon="Delete"
                  link
                  size="small"
                  type="danger"
                  title="删除"
                  @click.stop="handleDelete(data)"
                />
              </span>
            </div>
          </template>
        </el-tree>
      </el-card>

      <!-- 右侧：组织直属用户 -->
      <el-card class="org-users-card" shadow="never" v-loading="orgUsersLoading">
        <template #header>
          <span>{{ selectedOrg ? `「${selectedOrg.name}」直属用户` : '请选择组织' }}</span>
        </template>
        <el-table :data="orgUsers" border stripe size="small" empty-text="该组织暂无用户">
          <el-table-column prop="username" label="用户名" min-width="100" />
          <el-table-column prop="email" label="邮箱" min-width="160" />
          <el-table-column label="角色" width="90">
            <template #default="{ row }">
              {{ roleLabelMap[row.roleCode] ?? row.roleCode }}
            </template>
          </el-table-column>
          <el-table-column label="状态" width="80">
            <template #default="{ row }">
              <el-tag :type="row.status === 'active' ? 'success' : 'info'" size="small">
                {{ row.status === 'active' ? '启用' : '禁用' }}
              </el-tag>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </div>

    <!-- 移动组织对话框 -->
    <el-dialog
      v-model="moveDialogVisible"
      :title="`移动组织「${movingOrg?.name}」`"
      width="420px"
      :close-on-click-modal="false"
    >
      <el-form label-width="90px">
        <el-form-item label="目标父组织">
          <el-select
            v-model="moveTargetParentId"
            placeholder="请选择新的父组织"
            style="width: 100%"
          >
            <el-option
              v-for="opt in moveTargetOptions"
              :key="opt.id"
              :label="opt.name"
              :value="opt.id"
              :disabled="opt.disabled"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="moveDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleMoveConfirm">确定移动</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.org-management {
  padding: 24px;
  max-width: 1400px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.page-header h1 {
  margin: 0;
  font-size: 22px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.org-layout {
  display: grid;
  grid-template-columns: 480px 1fr;
  gap: 16px;
  align-items: start;
}

.tree-node {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-right: 8px;
}

.node-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.node-actions {
  display: none;
}

.tree-node:hover .node-actions {
  display: inline-flex;
}
</style>