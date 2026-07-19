import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {describe, expect, it} from 'vitest';
import {
  buildLearningPlanMarkdown,
  buildResourcePackageSummary,
  buildTaskTimeline,
  evaluationChangeSummary,
  fallbackLabel,
  needsDemoCaseConfirmation,
  profilePersonalizationEvidence,
  resourceFollowUpSuggestions,
  safeFailureMessage,
  shouldExitDemoMode,
  unansweredQuizCount,
} from './presentation';
import type {EvaluationResult, LearningPath, ProfileField, Resource, StudentProfile, TaskEvent, TaskState, UiAgentTrace} from '@/types/api';

function field<T>(value: T): ProfileField<T> {
  return {value, evidence: [], confidence: 0.9};
}

function profile(version: number, weakTopics: string[]): StudentProfile {
  return {
    student_id: 'private-student-id', version,
    major: field('人工智能'), course: field('机器学习'), knowledge_level: field('intermediate'),
    learning_goals: field(['完成分类项目']), weak_topics: field(weakTopics), learning_history: field([]),
    cognitive_style: field('案例导向'), language_preference: field('中文'), resource_preference: field(['代码实践']),
    time_budget: field({minutes_per_day: 60, days_per_week: 5}), evidence: [], confidence: 0.9,
    updated_at: '2026-07-19T00:00:00Z',
  };
}

function path(id: string, topics: string[], adjustmentReason: string | null = null): LearningPath {
  return {
    path_id: id, student_id: 'private-student-id', profile_version: 2, course: '机器学习', status: 'active',
    steps: topics.map((topic, index) => ({
      step: index + 1, topic, learning_goal: `掌握${topic}`, reason: '针对薄弱点', recommended_resources: ['coding'],
      completion_criteria: ['完成练习'], estimated_minutes: 45, prerequisites: [],
    })),
    adjustment_reason: adjustmentReason, generation_mode: 'llm_structured', created_at: '2026-07-19T00:00:00Z',
  };
}

function evaluation(): EvaluationResult {
  return {
    evaluation_id: 'private-evaluation-id', student_id: 'private-student-id', path_id: 'private-path-id', step: 1,
    mastery_score: 0.65, passed: false, weak_topics: ['模型评估'], feedback: '原始模型响应不应进入复制文本',
    profile_update_required: true, path_update_required: true, evaluated_at: '2026-07-19T00:00:00Z',
  };
}

function event(sequence: number, status: string, eventType: TaskEvent['event_type'] = 'task'): TaskEvent {
  return {
    event_id: `event-${sequence}`, task_id: 'task-1', sequence, event_type: eventType, status,
    progress: status === 'started' ? 20 : 100, message: `event ${sequence}`, agent: eventType === 'agent' ? 'quiz_agent' : 'orchestrator',
    resource_type: eventType === 'agent' ? 'quiz' : null, error: null, created_at: '2026-07-19T00:00:00Z',
  };
}

function task(status: TaskState['status']): TaskState {
  return {
    task_id: 'task-1', task_type: 'resource_generation', student_id: 'student', status, progress: 100,
    current_stage: 'finished', requested_resource_types: ['quiz'], result_resource_ids: [], agent_runs: [], errors: [],
    created_at: '2026-07-19T00:00:00Z', updated_at: '2026-07-19T00:00:01Z',
  };
}

const completedTraces: UiAgentTrace[] = [
  {key: 'retriever', name: 'Retriever', label: '', status: 'completed', message: '', progress: 40},
  ...['explanation_agent', 'mind_map_agent', 'quiz_agent', 'reading_agent', 'coding_agent'].map((key) => (
    {key, name: key, label: '', status: 'completed' as const, message: '', progress: 75}
  )),
  {key: 'reviewer_agent', name: 'Reviewer', label: '', status: 'completed', message: '', progress: 95},
];

describe('task progress presentation', () => {
  it('deduplicates sequence numbers and excludes heartbeat events from the business timeline', () => {
    const timeline = buildTaskTimeline([
      event(1, 'running'), event(1, 'running'), {...event(2, 'running'), event_type: 'heartbeat'}, event(3, 'completed'),
    ], task('completed'), completedTraces);

    expect(timeline[0].sequence).toBe(1);
    expect(timeline.at(-1)).toMatchObject({label: '学习方案已完成', status: 'completed', sequence: 3});
    expect(timeline.some((stage) => stage.sequence === 2)).toBe(false);
  });

  it('ends completed tasks in a stable completed state', () => {
    expect(buildTaskTimeline([event(4, 'completed')], task('completed'), completedTraces).at(-1)?.status).toBe('completed');
  });

  it('shows partial_success without treating it as a full success', () => {
    const timeline = buildTaskTimeline([event(4, 'partial_success')], task('partial_success'), completedTraces);
    expect(timeline.at(-1)).toMatchObject({label: '学习方案部分完成', status: 'partial'});
  });

  it('shows failed as terminal and suitable for a retry action', () => {
    const timeline = buildTaskTimeline([event(4, 'failed')], task('failed'), []);
    expect(timeline.at(-1)).toMatchObject({label: '学习方案未完成', status: 'failed'});
  });
});

describe('demo and evaluation presentation', () => {
  it('builds a safe resource package summary in the required learning order', () => {
    const resources = ['explanation', 'mind_map', 'reading', 'coding', 'quiz'].map((resourceType, index) => ({
      resource_id: `resource-${index}`, resource_type: resourceType, title: `资源 ${index}`, content: 'content',
      content_format: resourceType === 'quiz' ? 'json' : resourceType === 'mind_map' ? 'mermaid' : resourceType === 'coding' ? 'python' : 'markdown',
      target_topic: '逻辑回归', difficulty: 'intermediate', personalization_reason: '根据项目目标生成',
      source_references: [{source_id: index < 2 ? 'shared' : `source-${index}`, title: '课程资料', locator: `chapter-${index}`, chunk_id: null}],
      review_status: index === 4 ? 'needs_revision' : 'approved', created_at: '2026-07-19T00:00:00Z',
    })) as Resource[];
    const summary = buildResourcePackageSummary(resources, path('p1', ['逻辑回归']), 1, null, evaluation());

    expect(summary.completed).toBe(5);
    expect(summary.missingLabels).toEqual([]);
    expect(summary.recommendedOrder).toEqual(['课程讲解', '思维导图', '拓展阅读', '代码实践', '分层练习', '提交 Evaluation']);
    expect(summary.estimatedMinutes).toBe(45);
    expect(summary.approvedCount).toBe(4);
    expect(summary.evaluationLabel).toContain('65 分');
  });

  it('reports missing resources for partial_success without guessing time', () => {
    const partialTask: TaskState = {...task('partial_success'), requested_resource_types: ['explanation', 'quiz']};
    const summary = buildResourcePackageSummary([], null, 1, partialTask, null);
    expect(summary.partial).toBe(true);
    expect(summary.missingLabels).toHaveLength(5);
    expect(summary.estimatedMinutes).toBeNull();
  });

  it('derives visible personalization evidence only from current profile fields', () => {
    const evidence = profilePersonalizationEvidence(profile(2, ['模型评估']));
    expect(evidence).toContain('依据你的目标：完成分类项目');
    expect(evidence).toContain('依据你的薄弱点：模型评估');
    expect(evidence).toContain('依据你的时间预算：每天 60 分钟');
    expect(profilePersonalizationEvidence(null)).toEqual([]);
  });

  it('provides resource-specific follow-ups without sending anything', () => {
    expect(resourceFollowUpSuggestions('coding')).toContain('如何用于客户流失项目');
    expect(resourceFollowUpSuggestions('mind_map')).toHaveLength(3);
  });

  it('counts unanswered quiz items while preserving existing answers', () => {
    expect(unansweredQuizCount(['q1', 'q2', 'q3'], {q1: 'A', q2: '  '})).toBe(2);
  });

  it('requires confirmation before replacing a populated draft or appending to an existing conversation', () => {
    expect(needsDemoCaseConfirmation('', false)).toBe(false);
    expect(needsDemoCaseConfirmation('已有输入', false)).toBe(true);
    expect(needsDemoCaseConfirmation('', true)).toBe(true);
  });

  it('exits demo mode only for Escape while demo mode is active', () => {
    expect(shouldExitDemoMode('Escape', true)).toBe(true);
    expect(shouldExitDemoMode('Enter', true)).toBe(false);
    expect(shouldExitDemoMode('Escape', false)).toBe(false);
  });

  it('safely summarizes Evaluation changes when optional values are absent', () => {
    expect(evaluationChangeSummary(null, null, null, null, null)).toEqual({
      profileVersion: '暂无版本变化', addedWeakTopics: [], mastery: '尚未评价', pathSteps: '暂无路径变化', adjustmentReason: null, newFocus: [],
    });
  });

  it('shows profile version, strengthened weak topics, path count and adjustment reason', () => {
    const summary = evaluationChangeSummary(
      profile(1, ['逻辑回归']), profile(2, ['逻辑回归', '模型评估']),
      path('p1', ['逻辑回归']), path('p2', ['模型评估', '逻辑回归'], '优先巩固评价暴露的薄弱点'), evaluation(),
    );
    expect(summary).toMatchObject({profileVersion: 'v1 → v2', addedWeakTopics: ['模型评估'], pathSteps: '1 → 2 步'});
    expect(summary.adjustmentReason).toContain('薄弱点');
  });

  it('builds Markdown without internal IDs or the raw model feedback', () => {
    const resource = {
      resource_id: 'private-resource-id', resource_type: 'coding', title: '逻辑回归代码实践', content: 'secret raw output',
      content_format: 'python', target_topic: '逻辑回归', difficulty: 'intermediate', personalization_reason: '实践偏好',
      source_references: [], review_status: 'approved', created_at: '2026-07-19T00:00:00Z',
    } satisfies Resource;
    const markdown = buildLearningPlanMarkdown(profile(2, ['模型评估']), path('private-path-id', ['逻辑回归'], '评价后优先复习'), [resource], evaluation());

    expect(markdown).toContain('# EduAgent 个性化学习方案');
    expect(markdown).toContain('### 步骤 1');
    expect(markdown).toContain('- 学习主题：逻辑回归');
    expect(markdown).toContain('- 推荐资源类型：代码实践');
    expect(markdown).toContain('- 代码实践：逻辑回归代码实践');
    expect(markdown).toContain('评价后优先复习');
    expect(markdown).not.toContain('private-');
    expect(markdown).not.toContain('原始模型响应');
    expect(markdown).not.toContain('secret raw output');
  });

  it('keeps fallback labeling explicit and never calls it structured output', () => {
    expect(fallbackLabel('development_rule_based')).toBe('开发降级结果（非结构化模型输出）');
    expect(fallbackLabel('llm_structured')).toBeNull();
  });

  it('removes stack-shaped resource errors from the user-facing surface', () => {
    expect(safeFailureMessage('Traceback (most recent call last):\n  File "agent.py", line 2')).not.toContain('Traceback');
    expect(safeFailureMessage('coding agent timeout')).toBe('coding agent timeout');
  });

  it('keeps responsive and demo-mode safeguards in the shared stylesheet', () => {
    const stylePath = fileURLToPath(new URL('../styles/app.css', import.meta.url));
    const css = readFileSync(stylePath, 'utf8');
    expect(css).toContain('@media (max-width: 1280px)');
    expect(css).toContain('@media (max-height: 780px)');
    expect(css).toContain('@media (max-width: 760px)');
    expect(css).toContain('overflow-x: hidden');
    expect(css).toContain('.is-demo-mode');
    expect(css).toContain('repeat(6, minmax(145px, 1fr))');
  });
});
