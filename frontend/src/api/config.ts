export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');

export const API_ENDPOINTS = {
  health: '/api/health',
  profileChat: '/api/profile/chat',
  profile: (studentId: string) => `/api/profile/${encodeURIComponent(studentId)}`,
  pathGenerate: '/api/path/generate',
  resourcesGenerate: '/api/resources/generate',
  task: (taskId: string) => `/api/tasks/${encodeURIComponent(taskId)}`,
  resource: (resourceId: string) => `/api/resources/${encodeURIComponent(resourceId)}`,
  evaluation: '/api/evaluation/submit',
} as const;

export function absoluteApiUrl(path: string): string {
  return new URL(path, `${API_BASE_URL}/`).toString();
}
