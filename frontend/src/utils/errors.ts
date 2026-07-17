import axios from 'axios';
import type {ApiErrorBody} from '@/types/api';

const codeMessages: Record<string, string> = {
  PROFILE_NOT_FOUND: '尚未生成学习画像，请先完成一轮学习对话。',
  PATH_NOT_FOUND: '学习路径不存在，请重新生成路径。',
  RESOURCE_NOT_FOUND: '该资源暂时不可用，请重试生成。',
  VALIDATION_ERROR: '提交的信息格式不完整，请检查后重试。',
  EVALUATION_AGENT_NOT_IMPLEMENTED: '评价智能体尚未接入，答案已保留，请稍后重试。',
  EVALUATION_ERROR: '评价暂时未完成，请稍后重试。',
};

export function getApiErrorDetails(error: unknown): Record<string, unknown> {
  if (!axios.isAxiosError<ApiErrorBody>(error)) return {};
  return error.response?.data?.error?.details ?? {};
}

export function toUserMessage(error: unknown): string {
  if (axios.isAxiosError<ApiErrorBody>(error)) {
    if (error.code === 'ECONNABORTED') return '请求等待时间过长，请确认后端正在运行后重试。';
    if (!error.response) return '无法连接学习服务，请确认后端已启动并检查网络。';
    const body = error.response.data;
    const code = body?.error?.code;
    if (code && codeMessages[code]) return codeMessages[code];
    if (error.response.status >= 500) return '学习服务暂时异常，已有数据不会丢失，请稍后重试。';
    return body?.error?.message || `请求未完成（状态码 ${error.response.status}）。`;
  }
  if (error instanceof Error) return error.message || '操作未完成，请稍后重试。';
  return '操作未完成，请稍后重试。';
}

export function describeActualError(error: unknown): string {
  if (axios.isAxiosError<ApiErrorBody>(error)) {
    return JSON.stringify({status: error.response?.status, data: error.response?.data ?? null}, null, 2);
  }
  return error instanceof Error ? error.message : String(error);
}
