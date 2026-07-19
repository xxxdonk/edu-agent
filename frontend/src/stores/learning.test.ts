import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {createPinia, setActivePinia} from 'pinia';
import {ref} from 'vue';
import {api} from '@/api/client';
import {connectTaskEvents} from '@/api/sse';
import {useLearningStore} from './learning';
import type {EvaluationResult, LearningPath, ProfileChatResponse, ProfileField, Resource, TaskEvent, TaskState} from '@/types/api';

vi.mock('@/api/client', () => ({
  api: {
    health: vi.fn(),
    chat: vi.fn(),
    profile: vi.fn(),
    generatePath: vi.fn(),
    generateResources: vi.fn(),
    task: vi.fn(),
    resource: vi.fn(),
    evaluate: vi.fn(),
  },
}));

vi.mock('@/api/sse', () => ({
  connectTaskEvents: vi.fn(() => vi.fn()),
}));

function field<T>(value: T): ProfileField<T> {
  return {value, evidence: [], confidence: 1};
}

function profileResponse(
  version: number,
  nextQuestion: string,
  extractionMode: ProfileChatResponse['extraction_mode'] = 'llm_structured',
): ProfileChatResponse {
  return {
    profile: {
      student_id: 'demo-student-001',
      version,
      major: field('人工智能'),
      course: field('机器学习'),
      knowledge_level: field('intermediate' as const),
      learning_goals: field(['完成分类项目']),
      weak_topics: field(['梯度下降']),
      learning_history: field<string[]>([]),
      cognitive_style: field('案例与图示'),
      language_preference: field('zh-CN'),
      resource_preference: field(['coding', 'diagram']),
      time_budget: field({minutes_per_day: 45, days_per_week: 7}),
      evidence: [],
      confidence: 0.95,
      updated_at: '2026-07-16T00:00:00Z',
    },
    missing_dimensions: [],
    next_question: nextQuestion,
    is_complete: true,
    extraction_mode: extractionMode,
  };
}

function learningPath(version: number): LearningPath {
  return {
    path_id: `path-${version}`,
    student_id: 'demo-student-001',
    profile_version: version,
    course: '机器学习',
    status: 'active',
    steps: [{
      step: 1,
      topic: '梯度下降',
      learning_goal: '理解并实现梯度下降',
      reason: '针对薄弱点',
      recommended_resources: ['coding'],
      completion_criteria: ['完成代码练习'],
      estimated_minutes: 45,
      prerequisites: [],
    }],
    adjustment_reason: null,
    generation_mode: 'llm_structured',
    created_at: '2026-07-16T00:00:00Z',
  };
}

function quizResource(): Resource {
  return {
    resource_id: 'quiz-1',
    resource_type: 'quiz',
    title: '梯度下降练习',
    content: JSON.stringify({
      topic: '梯度下降',
      difficulty: 'intermediate',
      questions: [{
        id: 'q1', type: 'single_choice', level: 'basic', question: '学习率的作用是什么？',
        options: ['A. 控制更新步长', 'B. 增加样本'], answer: 'A', explanation: '学习率控制参数更新步长。',
      }],
    }),
    content_format: 'json',
    target_topic: '梯度下降',
    difficulty: 'intermediate',
    personalization_reason: '针对梯度下降薄弱点',
    source_references: [],
    review_status: 'approved',
    created_at: '2026-07-16T00:00:00Z',
  };
}

function evaluationResult(): EvaluationResult {
  return {
    evaluation_id: 'evaluation-1',
    student_id: 'demo-student-001',
    path_id: 'path-1',
    step: 1,
    mastery_score: 0.4,
    passed: false,
    weak_topics: ['梯度下降'],
    feedback: '需要继续复习梯度下降。',
    profile_update_required: true,
    path_update_required: true,
    evaluated_at: '2026-07-16T00:00:00Z',
  };
}

function terminalTask(status: TaskState['status'], resourceIds: string[], errors: string[]): TaskState {
  return {
    task_id: 'task-1',
    task_type: 'resource_generation',
    student_id: 'demo-student-001',
    status,
    progress: 100,
    current_stage: 'finished',
    requested_resource_types: ['quiz'],
    result_resource_ids: resourceIds,
    agent_runs: [],
    errors,
    created_at: '2026-07-16T00:00:00Z',
    updated_at: '2026-07-16T00:01:00Z',
  };
}

async function flushMicrotasks() {
  for (let index = 0; index < 4; index += 1) await Promise.resolve();
}

describe('learning store profile chat', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    setActivePinia(createPinia());
    vi.mocked(api.chat).mockReset();
    vi.mocked(api.profile).mockReset();
    vi.mocked(api.generatePath).mockReset();
    vi.mocked(api.generateResources).mockReset();
    vi.mocked(api.task).mockReset();
    vi.mocked(api.resource).mockReset();
    vi.mocked(api.evaluate).mockReset();
    vi.mocked(connectTaskEvents).mockReset();
    vi.mocked(connectTaskEvents).mockImplementation(() => vi.fn());
    vi.mocked(api.generatePath).mockImplementation(async (payload) => learningPath(payload.profile?.version ?? 1));
  });

  afterEach(() => {
    vi.clearAllTimers();
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('sends the latest user message with full history and renders replies without draft changes', async () => {
    const firstQuestion = '你更希望先看代码推导，还是先看梯度下降的图示？';
    const secondQuestion = '每周七天都可以安排四十五分钟吗？';
    vi.mocked(api.chat)
      .mockResolvedValueOnce(profileResponse(1, firstQuestion))
      .mockResolvedValueOnce(profileResponse(2, secondQuestion));

    const store = useLearningStore();
    const draft = ref('');
    const firstInput = '我是人工智能专业大二学生，目前在学习机器学习，梯度下降一直没弄懂。';
    const secondInput = '我偏好代码案例和图示。';

    const firstSend = store.sendMessage(firstInput);
    await flushMicrotasks();

    const firstPayload = vi.mocked(api.chat).mock.calls[0][0];
    expect(firstPayload.messages).toHaveLength(2);
    expect(firstPayload.messages.at(-1)).toMatchObject({role: 'user', content: firstInput});
    expect(store.messages.at(-1)?.streaming).toBe(true);

    const secondSend = store.sendMessage(secondInput);
    const secondPayload = vi.mocked(api.chat).mock.calls[1][0];
    expect(secondPayload.student_id).toBe(firstPayload.student_id);
    expect(secondPayload.messages).toHaveLength(4);
    expect(secondPayload.messages.slice(-3).map(({role, content}) => ({role, content}))).toEqual([
      {role: 'user', content: firstInput},
      {role: 'assistant', content: firstQuestion},
      {role: 'user', content: secondInput},
    ]);

    await flushMicrotasks();
    await vi.runAllTimersAsync();
    await Promise.all([firstSend, secondSend]);

    expect(draft.value).toBe('');
    expect(store.messages.at(-1)).toMatchObject({
      role: 'assistant',
      content: secondQuestion,
      streaming: false,
    });
  });

  it('sends only one profile request while profile extraction is loading', async () => {
    let resolveProfile!: (value: ProfileChatResponse) => void;
    vi.mocked(api.chat).mockImplementation(() => new Promise((resolve) => {
      resolveProfile = resolve;
    }));
    const store = useLearningStore();

    const first = store.sendMessage('第一次画像请求');
    await flushMicrotasks();
    const duplicate = store.sendMessage('加载期间不应重复发送');

    expect(api.chat).toHaveBeenCalledTimes(1);
    expect(store.profileStatus).toBe('loading');
    resolveProfile(profileResponse(1, '画像已完成。'));
    await flushMicrotasks();
    await vi.runAllTimersAsync();
    await Promise.all([first, duplicate]);

    expect(store.profileStatus).toBe('success');
  });

  it('aborts and ignores an old profile result after the session changes', async () => {
    let resolveOld!: (value: ProfileChatResponse) => void;
    vi.mocked(api.chat).mockImplementationOnce(() => new Promise((resolve) => {
      resolveOld = resolve;
    }));
    const store = useLearningStore();

    const oldRequest = store.sendMessage('即将被新会话替换的画像请求');
    await flushMicrotasks();
    const oldSignal = vi.mocked(api.chat).mock.calls[0][1];
    store.resetSession();
    resolveOld(profileResponse(13, '旧画像响应'));
    await oldRequest;

    expect(oldSignal?.aborted).toBe(true);
    expect(store.profile).toBeNull();
    expect(store.profileStatus).toBe('idle');
    expect(api.generatePath).not.toHaveBeenCalled();
  });

  it('clears the active assistant timeout when the session resets', async () => {
    vi.mocked(api.chat).mockResolvedValueOnce(profileResponse(1, '请补充一个足够长的问题以保持动画计时器处于活动状态。'));
    const store = useLearningStore();

    const sending = store.sendMessage('开始画像对话');
    await flushMicrotasks();
    expect(vi.getTimerCount()).toBe(1);

    store.resetSession();
    expect(vi.getTimerCount()).toBe(0);
    await sending;
    expect(store.messages).toHaveLength(1);
    expect(store.messages[0].role).toBe('assistant');
  });

  it('warns without throwing when heuristic extraction takes over', async () => {
    const warning = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    vi.mocked(api.chat).mockResolvedValueOnce(profileResponse(1, '请继续补充学习经历。', 'development_heuristic'));
    const store = useLearningStore();

    const sending = store.sendMessage('我的学习情况');
    await flushMicrotasks();
    await vi.runAllTimersAsync();
    await sending;

    expect(warning).toHaveBeenCalledWith(
      expect.stringContaining('结构化 LLM 未成功完成，本轮启发式接管，精确原因见后端 profile_fallback 日志'),
      expect.objectContaining({student_id: store.studentId}),
    );
    expect(store.profileStatus).toBe('success');
  });

  it('fills a demo case into the composer without sending or replacing conversation history', () => {
    const store = useLearningStore();
    const originalMessages = [...store.messages];
    const demoInput = '演示案例 B：考试复习与分层练习。';

    store.fillDemoCase(demoInput);

    expect(store.composerDraft).toBe(demoInput);
    expect(store.messages).toEqual(originalMessages);
    expect(api.chat).not.toHaveBeenCalled();
  });

  it('sends only one path request while planning and blocks profile submission', async () => {
    let resolvePath!: (value: LearningPath) => void;
    vi.mocked(api.generatePath).mockImplementation(() => new Promise((resolve) => {
      resolvePath = resolve;
    }));
    const store = useLearningStore();
    store.profile = profileResponse(1, '').profile;

    const first = store.generatePath();
    await flushMicrotasks();
    const duplicate = store.generatePath();
    await store.sendMessage('规划期间不应重复提交画像');

    expect(api.generatePath).toHaveBeenCalledTimes(1);
    expect(api.chat).not.toHaveBeenCalled();
    expect(store.pathStatus).toBe('loading');

    resolvePath(learningPath(1));
    await Promise.all([first, duplicate]);
    expect(store.pathStatus).toBe('success');
  });

  it('preserves the profile after timeout and allows one isolated retry', async () => {
    const timeoutError = Object.assign(new Error('timeout'), {
      isAxiosError: true,
      code: 'ECONNABORTED',
    });
    let resolveRetry!: (value: LearningPath) => void;
    vi.mocked(api.generatePath)
      .mockRejectedValueOnce(timeoutError)
      .mockImplementationOnce(() => new Promise((resolve) => {
        resolveRetry = resolve;
      }));
    const store = useLearningStore();
    const originalProfile = profileResponse(13, '').profile;
    store.profile = originalProfile;

    await store.generatePath();

    expect(store.pathStatus).toBe('error');
    expect(store.profile).toStrictEqual(originalProfile);
    expect(store.notice).toContain('后台可能仍在完成格式修复');

    const retry = store.generatePath();
    const duplicateRetry = store.generatePath();
    expect(api.generatePath).toHaveBeenCalledTimes(2);
    resolveRetry(learningPath(13));
    await Promise.all([retry, duplicateRetry]);

    expect(store.pathStatus).toBe('success');
    expect(store.notice).toBe('');
  });

  it('aborts and ignores an old path result after the session changes', async () => {
    let resolveOld!: (value: LearningPath) => void;
    const freshPath = {...learningPath(2), path_id: 'fresh-path'};
    vi.mocked(api.generatePath)
      .mockImplementationOnce(() => new Promise((resolve) => {
        resolveOld = resolve;
      }))
      .mockResolvedValueOnce(freshPath);
    const store = useLearningStore();
    store.profile = profileResponse(1, '').profile;

    const oldRequest = store.generatePath();
    await flushMicrotasks();
    const oldSignal = vi.mocked(api.generatePath).mock.calls[0][1];
    store.resetSession();
    expect(oldSignal?.aborted).toBe(true);

    store.profile = profileResponse(2, '').profile;
    await store.generatePath();
    resolveOld({...learningPath(1), path_id: 'stale-path'});
    await oldRequest;

    expect(store.path?.path_id).toBe('fresh-path');
    expect(store.pathStatus).toBe('success');
  });

  it('keeps the explicit development fallback mode returned by Planner', async () => {
    vi.mocked(api.generatePath).mockResolvedValue({
      ...learningPath(1),
      generation_mode: 'development_rule_based',
    });
    const store = useLearningStore();
    store.profile = profileResponse(1, '').profile;

    await store.generatePath();

    expect(store.path?.generation_mode).toBe('development_rule_based');
    expect(store.developmentMode).toBe(true);
  });

  it('enables and exits demo mode as refresh-local UI state', () => {
    const store = useLearningStore();
    expect(store.demoMode).toBe(false);
    store.setDemoMode(true);
    expect(store.demoMode).toBe(true);
    store.setDemoMode(false);
    expect(store.demoMode).toBe(false);
  });

  it('clears resources and evaluation when the selected path step changes', () => {
    const store = useLearningStore();
    const path = learningPath(1);
    path.steps.push({...path.steps[0], step: 2, topic: '逻辑回归'});
    store.path = path;
    store.resources = [quizResource()];
    store.evaluation = evaluationResult();
    store.resourceStatus = 'success';
    store.evaluationStatus = 'success';

    store.selectStep(2);

    expect(store.selectedStep).toBe(2);
    expect(store.resources).toEqual([]);
    expect(store.evaluation).toBeNull();
    expect(store.resourceStatus).toBe('idle');
    expect(store.evaluationStatus).toBe('idle');
  });

  it('clears stale resources and evaluation before regenerating the same step', async () => {
    vi.mocked(api.generateResources).mockResolvedValue({
      task_id: 'task-1',
      status: 'pending',
      status_url: '/api/tasks/task-1',
      events_url: '/api/tasks/task-1/events',
    });
    const store = useLearningStore();
    store.profile = profileResponse(1, '').profile;
    store.path = learningPath(1);
    store.resources = [quizResource()];
    store.evaluation = evaluationResult();
    store.resourceStatus = 'success';
    store.evaluationStatus = 'success';

    await store.startGeneration(true);

    expect(store.resources).toEqual([]);
    expect(store.evaluation).toBeNull();
    expect(store.evaluationStatus).toBe('idle');
    expect(api.generateResources).toHaveBeenCalledWith(expect.objectContaining({step: 1, regenerate: true}));
  });

  it('deduplicates resource events and keeps heartbeat out of the business timeline', async () => {
    vi.mocked(api.generateResources).mockResolvedValue({
      task_id: 'task-1', status: 'pending', status_url: '/api/tasks/task-1', events_url: '/api/tasks/task-1/events',
    });
    const store = useLearningStore();
    store.profile = profileResponse(1, '').profile;
    store.path = learningPath(1);
    await store.startGeneration();
    const handlers = vi.mocked(connectTaskEvents).mock.calls.at(-1)?.[1];
    const agentEvent: TaskEvent = {
      event_id: 'event-1', task_id: 'task-1', sequence: 1, event_type: 'agent', status: 'started', progress: 45,
      message: 'quiz generation started', agent: 'quiz_agent', resource_type: 'quiz', error: null, created_at: '2026-07-19T00:00:00Z',
    };
    handlers?.onEvent(agentEvent);
    handlers?.onEvent(agentEvent);
    handlers?.onEvent({...agentEvent, event_id: 'heartbeat-2', sequence: 2, event_type: 'heartbeat'});
    handlers?.onEvent({...agentEvent, event_id: 'review-3', sequence: 3, event_type: 'review', agent: 'explanation_agent'});

    expect(store.taskEvents).toHaveLength(2);
    expect(store.taskTimeline.find((stage) => stage.key === 'generation')?.resources?.find((item) => item.key === 'quiz_agent')?.status).toBe('running');
    expect(store.taskTimeline.find((stage) => stage.key === 'review')?.status).toBe('running');
    store.resetSession();
  });

  it('ignores a resource request that returns after the user switches steps', async () => {
    let resolveRequest!: (value: {
      task_id: string;
      status: 'pending';
      status_url: string;
      events_url: string;
    }) => void;
    vi.mocked(api.generateResources).mockImplementation(() => new Promise((resolve) => {
      resolveRequest = resolve;
    }));
    const store = useLearningStore();
    const path = learningPath(1);
    path.steps.push({...path.steps[0], step: 2, topic: '逻辑回归'});
    store.profile = profileResponse(1, '').profile;
    store.path = path;

    const generating = store.startGeneration();
    await flushMicrotasks();
    store.selectStep(2);
    resolveRequest({
      task_id: 'stale-task',
      status: 'pending',
      status_url: '/api/tasks/stale-task',
      events_url: '/api/tasks/stale-task/events',
    });
    await generating;

    expect(store.selectedStep).toBe(2);
    expect(store.task).toBeNull();
    expect(store.resourceStatus).toBe('idle');
    expect(vi.getTimerCount()).toBe(0);
  });

  it('adopts materialized evaluation updates without issuing duplicate chat or path requests', async () => {
    const refreshedProfile = profileResponse(2, '').profile;
    const updatedPath = {...learningPath(2), path_id: 'path-updated'};
    vi.mocked(api.profile).mockResolvedValue(refreshedProfile);
    vi.mocked(api.evaluate).mockResolvedValue({
      ...evaluationResult(),
      profile_update_suggestions: {
        updated_profile_version: 2,
        extraction_mode: 'llm_structured',
        evidence_source: 'evaluation',
      },
      path_update_suggestions: {
        new_path_id: updatedPath.path_id,
        updated_path: updatedPath,
        generation_mode: 'llm_structured',
      },
    } as EvaluationResult);
    const store = useLearningStore();
    store.profile = profileResponse(1, '').profile;
    store.path = learningPath(1);
    store.resources = [quizResource()];

    await store.submitEvaluation({q1: 'A'}, 12);

    expect(api.profile).toHaveBeenCalledWith(store.studentId);
    expect(api.chat).not.toHaveBeenCalled();
    expect(api.generatePath).not.toHaveBeenCalled();
    expect(store.previousProfile?.version).toBe(1);
    expect(store.profile?.version).toBe(2);
    expect(store.previousPath?.path_id).toBe('path-1');
    expect(store.path?.path_id).toBe('path-updated');
    expect(store.evaluationStatus).toBe('success');
  });

  it.each([
    {status: 'completed' as const, ids: ['quiz-1'], errors: [] as string[], expected: 'success'},
    {status: 'partial_success' as const, ids: ['quiz-1'], errors: ['coding failed'], expected: 'partial'},
    {status: 'failed' as const, ids: [] as string[], errors: ['all agents failed'], expected: 'error'},
  ])('finalizes a $status resource task as $expected', async ({status, ids, errors, expected}) => {
    vi.mocked(api.generateResources).mockResolvedValue({
      task_id: 'task-1',
      status: 'pending',
      status_url: '/api/tasks/task-1',
      events_url: '/api/tasks/task-1/events',
    });
    vi.mocked(api.task).mockResolvedValue(terminalTask(status, ids, errors));
    vi.mocked(api.resource).mockResolvedValue(quizResource());
    const store = useLearningStore();
    store.profile = profileResponse(1, '').profile;
    store.path = learningPath(1);

    await store.startGeneration();
    const handlers = vi.mocked(connectTaskEvents).mock.calls.at(-1)?.[1];
    expect(handlers).toBeDefined();
    handlers?.onTerminal();
    await flushMicrotasks();

    expect(store.resourceStatus).toBe(expected);
    expect(store.task?.status).toBe(status);
    expect(store.resources).toHaveLength(ids.length);
    store.resetSession();
  });

  it('allows an explicit retry after a failed terminal task', async () => {
    vi.mocked(api.generateResources).mockResolvedValue({
      task_id: 'task-1', status: 'pending', status_url: '/api/tasks/task-1', events_url: '/api/tasks/task-1/events',
    });
    vi.mocked(api.task).mockResolvedValue(terminalTask('failed', [], ['all agents failed']));
    const store = useLearningStore();
    store.profile = profileResponse(1, '').profile;
    store.path = learningPath(1);

    await store.startGeneration();
    vi.mocked(connectTaskEvents).mock.calls.at(-1)?.[1].onTerminal();
    await flushMicrotasks();
    expect(store.resourceStatus).toBe('error');

    await store.startGeneration(true);
    expect(api.generateResources).toHaveBeenCalledTimes(2);
    expect(api.generateResources).toHaveBeenLastCalledWith(expect.objectContaining({regenerate: true}));
    store.resetSession();
  });
});
