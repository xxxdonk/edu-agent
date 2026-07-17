import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {createPinia, setActivePinia} from 'pinia';
import {ref} from 'vue';
import {api} from '@/api/client';
import {useLearningStore} from './learning';
import type {LearningPath, ProfileChatResponse, ProfileField} from '@/types/api';

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

async function flushMicrotasks() {
  for (let index = 0; index < 4; index += 1) await Promise.resolve();
}

describe('learning store profile chat', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    setActivePinia(createPinia());
    vi.mocked(api.chat).mockReset();
    vi.mocked(api.generatePath).mockReset();
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
});
