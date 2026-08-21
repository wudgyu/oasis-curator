import request from '@/utils/request'
import type {
  IamGenerateResult,
  IamRoleItem,
  IamSaveRoleResult,
  IamTemplate,
} from '@/types'

/**
 * IAM 配置生成 API
 * 对接后端 /api/iam
 */

/** 查询预设权限模板 */
export async function fetchIamTemplates(): Promise<IamTemplate[]> {
  const { data } = await request.get<IamTemplate[]>('/iam/templates')
  return data
}

/** 自然语言生成 IAM 角色配置 */
export async function generateIamRole(
  requirement: string,
): Promise<IamGenerateResult> {
  const { data } = await request.post<IamGenerateResult>('/iam/generate-role', {
    requirement,
  })
  return data
}

/** 保存生成的 IAM 角色配置到数据库 */
export async function saveIamRole(
  config: Record<string, unknown>,
  overwrite = false,
): Promise<IamSaveRoleResult> {
  const { data } = await request.post<IamSaveRoleResult>('/iam/save-role', {
    config,
    overwrite,
  })
  return data
}

/** 查询角色列表（内置 + 当前租户自定义） */
export async function fetchIamRoles(): Promise<IamRoleItem[]> {
  const { data } = await request.get<IamRoleItem[]>('/iam/roles')
  return data
}

/** 删除自定义角色 */
export async function deleteIamRole(roleId: string): Promise<void> {
  await request.delete(`/iam/roles/${roleId}`)
}
