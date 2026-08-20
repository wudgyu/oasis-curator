import request from '@/utils/request'
import type { IamGenerateResult, IamTemplate } from '@/types'

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
