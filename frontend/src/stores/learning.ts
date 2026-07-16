import {computed, ref} from 'vue';
import {defineStore} from 'pinia';
import {api} from '@/api/client';
import {API_ENDPOINTS} from '@/api/config';
import {connectTaskEvents} from '@/api/sse';
import {describeActualError, getApiErrorDetails, toUserMessage} from '@/utils/errors';
import {parseQuiz} from '@/utils/content';
import type {
  ApiIssue,
  ChatMessage,
  EvaluationResult,
  LearningPath,
  ProfileChatResponse,
  Resource,
  ResourceType,
  StudentProfile,
  TaskEvent,
  TaskState,
  UiAgentStatus,
  UiAgentTrace,
  ViewStatus,
} from '@/types/api';

interface UiChatMessage extends ChatMessage {
  streaming?: boolean;
  pending?: boolean;
}

const resourceTypes: ResourceType[] = ['explanation', 'mind_map', 'quiz', 'reading', 'coding'];
const terminalStatuses = new Set(['completed', 'partial_success', 'failed']);

const traceTemplate: UiAgentTrace[] = [
  {key: 'profile_agent', name: 'Profile Agent', label: '正在分析学生画像', status: 'waiting', message: '等待学习对话', progress: 0},
  {key: 'planner_agent', name: 'Planner Agent', label: '正在规划学习路径', status: 'waiting', message: '等待画像完成', progress: 0},
  {key: 'retriever', name: 'Retriever', label: '正在检索课程资料', status: 'waiting', message: '等待资源任务', progress: 0},
  {key: 'explanation_agent', name: 'Explanation Agent', label: '正在生成课程讲解', status: 'waiting', message: '等待编排', progress: 0},
  {key: 'mind_map_agent', name: 'MindMap Agent', label: '正在生成思维导图', status: 'waiting', message: '等待编排', progress: 0},
  {key: 'quiz_agent', name: 'Quiz Agent', label: '正在生成练习题', status: 'waiting', message: '等待编排', progress: 0},
  {key: 'reading_agent', name: 'Reading Agent', label: '正在生成拓展阅读', status: 'waiting', message: '等待编排', progress: 0},
  {key: 'coding_agent', name: 'Coding Agent', label: '正在生成代码案例', status: 'waiting', message: '等待编排', progress: 0},
  {key: 'reviewer_agent', name: 'Reviewer Agent', label: '正在审校', status: 'waiting', message: '等待资源生成', progress: 0},
  {key: 'system', name: 'Orchestrator', label: '已完成', status: 'waiting', message: '等待任务完成', progress: 0},
];

function id(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function normalizeAgentKey(event: TaskEvent): string {
  const raw = (event.agent || '').toLowerCase();
  if (raw.includes('explanation')) return 'explanation_agent';
  if (raw.includes('mind')) return 'mind_map_agent';
  if (raw.includes('quiz')) return 'quiz_agent';
  if (raw.includes('reading')) return 'reading_agent';
  if (raw.includes('coding')) return 'coding_agent';
  if (raw.includes('review')) return 'reviewer_agent';
  return event.event_type === 'review' ? 'reviewer_agent' : 'system';
}

function normalizeStatus(status: string): UiAgentStatus {
  if (status === 'started' || status === 'running') return 'running';
  if (status === 'completed' || status === 'partial_success') return 'completed';
  if (status === 'failed' || status === 'skipped') return 'failed';
  return 'waiting';
}

export const useLearningStore = defineStore('learning', () => {
  const studentId = ref('demo-student-001');
  const conversationId = ref(id('conversation'));
  const messages = ref<UiChatMessage[]>([
    {
      message_id: id('assistant'),
      role: 'assistant',
      content: '你好，我会通过对话了解你的学习情况。可以告诉我你的专业、正在学习的课程、薄弱点、目标和每周可用时间。',
    },
  ]);
  const profile = ref<StudentProfile | null>(null);
  const previousProfile = ref<StudentProfile | null>(null);
  const profileMeta = ref<Pick<ProfileChatResponse, 'missing_dimensions' | 'next_question' | 'is_complete' | 'extraction_mode'> | null>(null);
  const path = ref<LearningPath | null>(null);
  const previousPath = ref<LearningPath | null>(null);
  const selectedStep = ref(1);
  const resources = ref<Resource[]>([]);
  const resourceFailures = ref<string[]>([]);
  const task = ref<TaskState | null>(null);
  const taskEvents = ref<TaskEvent[]>([]);
  const traces = ref<UiAgentTrace[]>(traceTemplate.map((item) => ({...item})));
  const evaluation = ref<EvaluationResult | null>(null);
  const apiIssues = ref<ApiIssue[]>([]);
  const healthStatus = ref<ViewStatus>('idle');
  const profileStatus = ref<ViewStatus>('idle');
  const pathStatus = ref<ViewStatus>('idle');
  const resourceStatus = ref<ViewStatus>('idle');
  const evaluationStatus = ref<ViewStatus>('idle');
  const healthMessage = ref('尚未检查后端连接');
  const notice = ref('');

  let closeStream: (() => void) | null = null;
  let pollingTimer: number | null = null;
  let finalizingTask = false;

  const quiz = computed(() => parseQuiz(resources.value.find((item) => item.resource_type === 'quiz')));
  const developmentMode = computed(() =>
    profileMeta.value?.extraction_mode.startsWith('development_') || path.value?.generation_mode.startsWith('development_'),
  );
  const hasCoreContext = computed(() => Boolean(profile.value && path.value));

  function setTrace(key: string, status: UiAgentStatus, message: string, progress?: number, error?: string) {
    const trace = traces.value.find((item) => item.key === key);
    if (!trace) return;
    trace.status = status;
    trace.message = message;
    trace.progress = progress ?? trace.progress;
    trace.error = error;
  }

  function resetResourceTraces() {
    const preserved = new Set(['profile_agent', 'planner_agent']);
    traces.value = traceTemplate.map((item) => {
      const current = traces.value.find((trace) => trace.key === item.key);
      return preserved.has(item.key) && current ? {...current} : {...item};
    });
  }

  function recordIssue(endpoint: string, request: unknown, expected: string, error: unknown, reproduction: string[]) {
    apiIssues.value.unshift({
      endpoint,
      request,
      expected,
      actual: describeActualError(error),
      browserError: toUserMessage(error),
      reproduction,
      createdAt: new Date().toISOString(),
    });
  }

  async function checkHealth() {
    healthStatus.value = 'loading';
    try {
      const result = await api.health();
      healthStatus.value = result.status === 'ok' ? 'success' : 'partial';
      healthMessage.value = `后端 ${result.version} · 数据库 ${result.database} · ${result.environment}`;
    } catch (error) {
      healthStatus.value = 'error';
      healthMessage.value = toUserMessage(error);
      recordIssue(API_ENDPOINTS.health, {}, '200 HealthResponse', error, ['启动后端', '打开前端', '点击“检查连接”']);
    }
  }

  async function animateAssistant(text: string) {
    const target: UiChatMessage = {message_id: id('assistant'), role: 'assistant', content: '', streaming: true};
    messages.value.push(target);
    const chunks = Array.from(text);
    const batchSize = Math.max(1, Math.ceil(chunks.length / 35));
    for (let index = 0; index < chunks.length; index += batchSize) {
      target.content += chunks.slice(index, index + batchSize).join('');
      await new Promise((resolve) => window.setTimeout(resolve, 18));
    }
    target.streaming = false;
  }

  function apiMessages(): ChatMessage[] {
    return messages.value
      .filter((message) => !message.pending && message.content.trim())
      .map(({message_id, role, content}) => ({message_id, role, content}));
  }

  async function sendMessage(content: string) {
    const trimmed = content.trim();
    if (!trimmed || profileStatus.value === 'loading') return;
    messages.value.push({message_id: id('user'), role: 'user', content: trimmed});
    profileStatus.value = 'loading';
    notice.value = '';
    setTrace('profile_agent', 'running', '正在从自然语言中提取画像证据', 12);
    const payload = {
      student_id: studentId.value,
      conversation_id: conversationId.value,
      messages: apiMessages(),
      evaluation_summary: null,
    };
    try {
      const response = await api.chat(payload);
      previousProfile.value = profile.value;
      profile.value = response.profile;
      profileMeta.value = response;
      profileStatus.value = 'success';
      setTrace('profile_agent', 'completed', `画像 v${response.profile.version} 已生成`, 20);
      const answer = response.next_question || '画像已更新。我将根据这些信息为你安排下一步学习路径。';
      await animateAssistant(answer);
      await generatePath();
    } catch (error) {
      profileStatus.value = 'error';
      notice.value = toUserMessage(error);
      setTrace('profile_agent', 'failed', notice.value, 0, notice.value);
      recordIssue(API_ENDPOINTS.profileChat, payload, '200 ProfileChatResponse，包含字段证据与置信度', error, [
        '在学习画像工作区输入学习情况', '点击发送', '观察画像与自然语言追问',
      ]);
    }
  }

  async function generatePath(evaluationSummary: string | null = null) {
    if (!profile.value || pathStatus.value === 'loading') return;
    pathStatus.value = 'loading';
    setTrace('planner_agent', 'running', '正在结合画像、薄弱点和时间预算规划路径', 24);
    const payload = {
      student_id: studentId.value,
      profile: profile.value,
      previous_path_id: evaluationSummary ? path.value?.path_id ?? null : null,
      evaluation_summary: evaluationSummary,
    };
    try {
      const result = await api.generatePath(payload);
      if (path.value) previousPath.value = path.value;
      path.value = result;
      selectedStep.value = result.steps[0]?.step ?? 1;
      pathStatus.value = result.steps.length ? 'success' : 'empty';
      setTrace('planner_agent', 'completed', `已生成 ${result.steps.length} 个学习步骤`, 30);
    } catch (error) {
      pathStatus.value = 'error';
      notice.value = toUserMessage(error);
      setTrace('planner_agent', 'failed', notice.value, 20, notice.value);
      recordIssue(API_ENDPOINTS.pathGenerate, payload, '200 { path: LearningPath }', error, [
        '完成画像对话', '等待自动生成学习路径', '观察路径工作区',
      ]);
    }
  }

  function applyTaskEvent(event: TaskEvent) {
    if (taskEvents.value.some((item) => item.sequence === event.sequence)) return;
    taskEvents.value.push(event);
    taskEvents.value.sort((a, b) => a.sequence - b.sequence);
    if (event.event_type === 'agent' || event.event_type === 'review') {
      if (event.status === 'started') setTrace('retriever', 'completed', '课程知识库检索已完成', Math.min(event.progress, 38));
      const key = normalizeAgentKey(event);
      setTrace(key, normalizeStatus(event.status), event.message, event.progress, event.error ?? undefined);
    }
    if (event.event_type === 'task') {
      setTrace('system', normalizeStatus(event.status), event.message, event.progress, event.error ?? undefined);
    }
  }

  function stopTaskMonitoring() {
    closeStream?.();
    closeStream = null;
    if (pollingTimer !== null) window.clearInterval(pollingTimer);
    pollingTimer = null;
  }

  async function finalizeTask(taskId: string) {
    if (finalizingTask) return;
    finalizingTask = true;
    try {
      const result = await api.task(taskId);
      task.value = result;
      if (!terminalStatuses.has(result.status)) return;
      stopTaskMonitoring();
      const settled = await Promise.allSettled(result.result_resource_ids.map((resourceId) => api.resource(resourceId)));
      resources.value = settled.flatMap((entry) => entry.status === 'fulfilled' ? [entry.value] : []);
      resourceFailures.value = [
        ...result.errors,
        ...settled.flatMap((entry) => entry.status === 'rejected' ? [toUserMessage(entry.reason)] : []),
      ];
      if (result.status === 'failed' || resources.value.length === 0) resourceStatus.value = 'error';
      else if (result.status === 'partial_success' || resourceFailures.value.length) resourceStatus.value = 'partial';
      else resourceStatus.value = 'success';
      setTrace('system', result.status === 'failed' ? 'failed' : 'completed', result.current_stage, result.progress, result.errors.join('；'));
    } catch (error) {
      resourceStatus.value = 'error';
      notice.value = toUserMessage(error);
      recordIssue(API_ENDPOINTS.task(taskId), {task_id: taskId}, 'TaskState 终态及资源 ID', error, [
        '创建资源生成任务', '等待 SSE 结束', '读取任务结果',
      ]);
    } finally {
      finalizingTask = false;
    }
  }

  async function startGeneration(regenerate = false) {
    if (!profile.value || !path.value || resourceStatus.value === 'loading') return;
    stopTaskMonitoring();
    resetResourceTraces();
    resources.value = [];
    resourceFailures.value = [];
    taskEvents.value = [];
    resourceStatus.value = 'loading';
    notice.value = '';
    setTrace('retriever', 'running', '正在检索课程知识库与来源片段', 32);
    const payload = {
      student_id: studentId.value,
      path_id: path.value.path_id,
      step: selectedStep.value,
      resource_types: resourceTypes,
      regenerate,
    };
    try {
      const accepted = await api.generateResources(payload);
      task.value = {
        task_id: accepted.task_id, task_type: 'resource_generation', student_id: studentId.value,
        status: accepted.status, progress: 0, current_stage: '任务已创建', requested_resource_types: resourceTypes,
        result_resource_ids: [], agent_runs: [], errors: [], created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
      };
      closeStream = connectTaskEvents(accepted.events_url, {
        onEvent: applyTaskEvent,
        onTerminal: () => void finalizeTask(accepted.task_id),
        onError: (message) => { notice.value = message; },
      });
      pollingTimer = window.setInterval(async () => {
        try {
          const state = await api.task(accepted.task_id);
          task.value = state;
          if (terminalStatuses.has(state.status)) await finalizeTask(accepted.task_id);
        } catch {
          // SSE remains the primary channel; polling errors are handled by final task retrieval.
        }
      }, 2500);
    } catch (error) {
      resourceStatus.value = 'error';
      notice.value = toUserMessage(error);
      setTrace('retriever', 'failed', notice.value, 30, notice.value);
      recordIssue(API_ENDPOINTS.resourcesGenerate, payload, '202 TaskAcceptedResponse，随后通过 SSE 返回进度', error, [
        '生成画像与学习路径', '选择路径步骤', '点击“生成五类资源”',
      ]);
    }
  }

  async function submitEvaluation(answers: Record<string, string>, timeSpentMinutes: number) {
    if (!path.value || !quiz.value || evaluationStatus.value === 'loading') return;
    evaluationStatus.value = 'loading';
    notice.value = '';
    const payload = {
      student_id: studentId.value,
      path_id: path.value.path_id,
      step: selectedStep.value,
      answers: quiz.value.questions.map((question) => ({question_id: question.id, response: answers[question.id] ?? ''})),
      time_spent_minutes: timeSpentMinutes,
    };
    try {
      const result = await api.evaluate(payload);
      evaluation.value = result;
      evaluationStatus.value = 'success';
      if (result.profile_update_required || result.path_update_required) {
        const summary = `${result.feedback}\n薄弱知识点：${result.weak_topics.join('、') || '无'}`;
        previousProfile.value = profile.value;
        previousPath.value = path.value;
        const profileResponse = await api.chat({
          student_id: studentId.value,
          conversation_id: conversationId.value,
          messages: apiMessages(),
          evaluation_summary: summary,
        });
        profile.value = profileResponse.profile;
        profileMeta.value = profileResponse;
        await generatePath(summary);
      }
    } catch (error) {
      evaluationStatus.value = 'error';
      notice.value = toUserMessage(error);
      const details = getApiErrorDetails(error);
      if (details.mock === true) notice.value = `开发接口提示：${notice.value}`;
      recordIssue(API_ENDPOINTS.evaluation, payload, '200 EvaluationResult；失败时不得返回伪造评价', error, [
        '生成 quiz 资源', '完成所有题目', '点击“提交评价”',
      ]);
    }
  }

  function resetSession() {
    stopTaskMonitoring();
    studentId.value = `demo-student-${Date.now()}`;
    conversationId.value = id('conversation');
    messages.value = [{
      message_id: id('assistant'), role: 'assistant',
      content: '新的学习会话已开始。请自然地介绍你的学习情况，我会逐步完善画像。',
    }];
    profile.value = null;
    previousProfile.value = null;
    profileMeta.value = null;
    path.value = null;
    previousPath.value = null;
    resources.value = [];
    resourceFailures.value = [];
    task.value = null;
    taskEvents.value = [];
    evaluation.value = null;
    traces.value = traceTemplate.map((item) => ({...item}));
    profileStatus.value = pathStatus.value = resourceStatus.value = evaluationStatus.value = 'idle';
    notice.value = '';
  }

  return {
    studentId, messages, profile, previousProfile, profileMeta, path, previousPath, selectedStep,
    resources, resourceFailures, task, taskEvents, traces, evaluation, apiIssues, healthStatus,
    profileStatus, pathStatus, resourceStatus, evaluationStatus, healthMessage, notice, quiz,
    developmentMode, hasCoreContext, checkHealth, sendMessage, generatePath, startGeneration,
    submitEvaluation, resetSession,
  };
});
