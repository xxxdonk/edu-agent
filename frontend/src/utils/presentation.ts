import type {
  EvaluationResult,
  LearningPath,
  Resource,
  StudentProfile,
  TaskEvent,
  TaskState,
  UiAgentStatus,
  UiAgentTrace,
} from '@/types/api';

export type TimelineStatus = 'waiting' | 'running' | 'completed' | 'partial' | 'failed';

export interface TimelineResourceState {
  key: string;
  label: string;
  status: TimelineStatus;
}

export interface TimelineStage {
  key: 'start' | 'rag' | 'generation' | 'review' | 'persist' | 'finish';
  label: string;
  description: string;
  status: TimelineStatus;
  sequence: number | null;
  resources?: TimelineResourceState[];
}

export interface EvaluationChangeSummary {
  profileVersion: string;
  addedWeakTopics: string[];
  mastery: string;
  pathSteps: string;
  adjustmentReason: string | null;
  newFocus: string[];
}

const terminalStatuses = new Set(['completed', 'partial_success', 'failed']);
const resourceTypeLabels = {
  explanation: '课程讲解', mind_map: '思维导图', quiz: '分层练习', reading: '拓展阅读', coding: '代码实践',
} as const;
const resourceTraceKeys = [
  ['explanation_agent', '课程讲解'],
  ['mind_map_agent', '思维导图'],
  ['quiz_agent', '分层练习'],
  ['reading_agent', '拓展阅读'],
  ['coding_agent', '代码实践'],
] as const;

function timelineStatus(status: string | undefined): TimelineStatus {
  if (status === 'failed' || status === 'skipped') return 'failed';
  if (status === 'partial_success') return 'partial';
  if (status === 'completed') return 'completed';
  if (status === 'started' || status === 'running' || status === 'pending') return 'running';
  return 'waiting';
}

function traceStatus(status: UiAgentStatus | undefined): TimelineStatus {
  return timelineStatus(status);
}

function aggregateStatuses(statuses: TimelineStatus[]): TimelineStatus {
  if (!statuses.length || statuses.every((status) => status === 'waiting')) return 'waiting';
  if (statuses.some((status) => status === 'running')) return 'running';
  if (statuses.every((status) => status === 'failed')) return 'failed';
  if (statuses.some((status) => status === 'failed' || status === 'partial')) return 'partial';
  if (statuses.every((status) => status === 'completed')) return 'completed';
  return 'running';
}

function latestSequence(events: TaskEvent[], predicate: (event: TaskEvent) => boolean): number | null {
  return events.filter(predicate).at(-1)?.sequence ?? null;
}

function taskEventIdentity(event: TaskEvent): string {
  const sequence = Number(event.sequence);
  if (Number.isFinite(sequence)) return `sequence:${sequence}`;
  if (event.event_id) return `event:${event.event_id}`;
  return [event.event_type, event.status, event.agent, event.resource_type, event.created_at, event.message].join('|');
}

export function buildTaskTimeline(
  rawEvents: TaskEvent[],
  task: TaskState | null,
  traces: UiAgentTrace[] = [],
): TimelineStage[] {
  const seenEvents = new Set<string>();
  const events: TaskEvent[] = [];
  for (const event of rawEvents) {
    if (event.event_type === 'heartbeat') continue;
    const identity = taskEventIdentity(event);
    if (seenEvents.has(identity)) continue;
    seenEvents.add(identity);
    events.push(event);
  }
  events.sort((left, right) => {
    const leftSequence = Number(left.sequence);
    const rightSequence = Number(right.sequence);
    if (Number.isFinite(leftSequence) && Number.isFinite(rightSequence)) return leftSequence - rightSequence;
    return left.created_at.localeCompare(right.created_at) || left.event_id.localeCompare(right.event_id);
  });
  const traceByKey = new Map(traces.map((trace) => [trace.key, trace]));
  const terminalEvent = [...events].reverse().find((event) => event.event_type === 'task' && terminalStatuses.has(event.status));
  const terminalStatus = terminalEvent?.status ?? (task && terminalStatuses.has(task.status) ? task.status : undefined);
  const hasTask = Boolean(task || events.length);

  const resources = resourceTraceKeys.map(([key, label]) => ({
    key,
    label,
    status: traceStatus(traceByKey.get(key)?.status),
  }));
  const generationStatus = aggregateStatuses(resources.map((resource) => resource.status));
  const reviewStatus = traceStatus(traceByKey.get('reviewer_agent')?.status);
  const ragStatus = traceStatus(traceByKey.get('retriever')?.status);
  const finishStatus = timelineStatus(terminalStatus);
  const persistStatus: TimelineStatus = terminalStatus
    ? (terminalStatus === 'failed' ? 'failed' : terminalStatus === 'partial_success' ? 'partial' : 'completed')
    : reviewStatus === 'completed' ? 'running' : 'waiting';

  return [
    {
      key: 'start', label: '任务已启动', description: hasTask ? '学习资源任务已经创建' : '等待创建学习资源任务',
      status: hasTask ? 'completed' : 'waiting', sequence: events[0]?.sequence ?? null,
    },
    {
      key: 'rag', label: '课程知识检索', description: ragStatus === 'completed' ? 'RAG 课程来源已经就绪' : '正在检索课程章节与相关片段',
      status: ragStatus, sequence: latestSequence(events, (event) => /retriev|rag/i.test(`${event.agent ?? ''} ${event.message}`)),
    },
    {
      key: 'generation', label: '学习资源生成', description: '五类资源正在并行生成',
      status: generationStatus, sequence: latestSequence(events, (event) => event.event_type === 'agent'), resources,
    },
    {
      key: 'review', label: '资源质量审校', description: 'Reviewer 正在逐项检查质量、引用与安全性',
      status: reviewStatus, sequence: latestSequence(events, (event) => event.event_type === 'review' || /review/i.test(event.agent ?? '')),
    },
    {
      key: 'persist', label: '保存学习结果', description: persistStatus === 'waiting' ? '等待资源审校完成' : '正在保存合格资源与最终状态',
      status: persistStatus, sequence: terminalEvent?.sequence ?? null,
    },
    {
      key: 'finish', label: terminalStatus === 'partial_success' ? '学习方案部分完成' : terminalStatus === 'failed' ? '学习方案未完成' : '学习方案已完成',
      description: terminalStatus ? '本次任务已经结束' : '等待全部阶段结束',
      status: finishStatus, sequence: terminalEvent?.sequence ?? null,
    },
  ];
}

function fieldValue<T>(field: {value: T} | undefined): T | undefined {
  return field?.value;
}

function textList(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String).map((item) => item.trim()).filter(Boolean) : [];
}

function safeText(value: unknown, fallback = '未提供'): string {
  if (value === null || value === undefined || value === '') return fallback;
  if (Array.isArray(value)) return value.length ? value.join('、') : fallback;
  return String(value);
}

export function evaluationChangeSummary(
  beforeProfile: StudentProfile | null,
  afterProfile: StudentProfile | null,
  beforePath: LearningPath | null,
  afterPath: LearningPath | null,
  evaluation: EvaluationResult | null,
): EvaluationChangeSummary {
  const oldWeak = new Set(textList(fieldValue(beforeProfile?.weak_topics)));
  const currentWeak = textList(fieldValue(afterProfile?.weak_topics));
  return {
    profileVersion: beforeProfile && afterProfile ? `v${beforeProfile.version} → v${afterProfile.version}` : afterProfile ? `v${afterProfile.version}` : '暂无版本变化',
    addedWeakTopics: currentWeak.filter((topic) => !oldWeak.has(topic)),
    mastery: evaluation ? `${Math.round(evaluation.mastery_score * 100)} 分 · ${evaluation.passed ? '已掌握' : '需巩固'}` : '尚未评价',
    pathSteps: beforePath && afterPath ? `${beforePath.steps.length} → ${afterPath.steps.length} 步` : afterPath ? `${afterPath.steps.length} 步` : '暂无路径变化',
    adjustmentReason: afterPath?.adjustment_reason ?? null,
    newFocus: afterPath?.steps.slice(0, 3).map((step) => step.topic).filter(Boolean) ?? [],
  };
}

export function buildLearningPlanMarkdown(
  profile: StudentProfile | null,
  path: LearningPath | null,
  resources: Resource[],
  evaluation: EvaluationResult | null,
): string {
  const lines = ['# EduAgent 个性化学习方案', ''];
  if (profile) {
    const budget = fieldValue(profile.time_budget);
    lines.push(
      '## 学生画像摘要', '',
      `- 专业：${safeText(fieldValue(profile.major))}`,
      `- 课程：${safeText(fieldValue(profile.course))}`,
      `- 知识水平：${safeText(fieldValue(profile.knowledge_level))}`,
      `- 学习目标：${safeText(fieldValue(profile.learning_goals))}`,
      `- 薄弱知识点：${safeText(fieldValue(profile.weak_topics), '暂无')}`,
      `- 资源偏好：${safeText(fieldValue(profile.resource_preference))}`,
      `- 学习时间：${budget ? `每天 ${budget.minutes_per_day} 分钟，每周 ${budget.days_per_week} 天` : '未提供'}`,
      '',
    );
  }
  if (path) {
    lines.push('## 当前学习路径', '');
    for (const step of [...path.steps].sort((left, right) => left.step - right.step)) {
      lines.push(
        `### 步骤 ${step.step}`, '',
        `- 学习主题：${step.topic}`,
        `- 学习目标：${step.learning_goal}`,
        `- 预计时间：${step.estimated_minutes} 分钟`,
        `- 推荐资源类型：${step.recommended_resources.map((type) => resourceTypeLabels[type]).join('、') || '本次未返回该项'}`,
        '',
      );
    }
  }
  if (resources.length) {
    lines.push('## 已生成资源', '', ...resources.map((resource) => `- ${resourceTypeLabels[resource.resource_type]}：${resource.title}`), '');
  }
  if (evaluation) {
    lines.push(
      '## Evaluation 摘要', '',
      `- 掌握度：${Math.round(evaluation.mastery_score * 100)} 分`,
      `- 结果：${evaluation.passed ? '已通过' : '需要巩固'}`,
      `- 薄弱知识点：${evaluation.weak_topics.join('、') || '本轮未发现明显薄弱点'}`,
      '',
    );
  }
  if (path?.adjustment_reason) lines.push('## 重新规划原因', '', path.adjustment_reason, '');
  return lines.join('\n').trimEnd();
}

export function needsDemoCaseConfirmation(draft: string, hasUserConversation: boolean): boolean {
  return Boolean(draft.trim() || hasUserConversation);
}

export function shouldExitDemoMode(key: string, demoMode: boolean): boolean {
  return demoMode && key === 'Escape';
}

export function fallbackLabel(mode: string | null | undefined): string | null {
  return mode?.startsWith('development_') ? '开发降级结果（非结构化模型输出）' : null;
}

export function safeFailureMessage(message: string): string {
  if (/traceback|\bfile\s+".+"\s*,\s*line\s+\d+|stack trace/i.test(message)) {
    return '资源生成过程中出现内部错误，详细信息已由服务端记录。';
  }
  return message.split(/\r?\n/, 1)[0].trim().slice(0, 180) || '该资源暂时未生成成功。';
}
