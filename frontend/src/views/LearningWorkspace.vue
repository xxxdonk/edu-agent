<template>
  <main class="app-shell" :class="{'is-demo-mode': store.demoMode}">
    <header class="app-header">
      <div class="brand-block">
        <div class="brand-mark">EA</div>
        <div><p>智能学习闭环 · 从需求理解到动态调整</p><h1>EduAgent 个性化学习工作台</h1></div>
      </div>
      <div class="header-actions">
        <el-tag v-if="store.developmentMode" type="warning" effect="plain">降级模式（非结构化模型结果）</el-tag>
        <div class="health-chip developer-only" :class="`health-chip--${store.healthStatus}`"><span />{{ store.healthMessage }}</div>
        <el-button
          :icon="CopyDocument"
          :disabled="!canCopyPlan"
          :title="canCopyPlan ? '复制不含内部 ID 的 Markdown 学习方案' : '生成画像或路径后可复制'"
          @click="copyLearningPlan"
        >复制学习方案</el-button>
        <el-button v-if="!store.demoMode" :icon="Monitor" @click="store.setDemoMode(true)">演示模式</el-button>
        <el-button v-else type="primary" plain @click="store.setDemoMode(false)">退出演示</el-button>
        <el-button class="developer-only" :icon="Connection" :loading="store.healthStatus === 'loading'" @click="store.checkHealth">检查连接</el-button>
        <el-button class="secondary-action" :icon="RefreshLeft" @click="store.resetSession">新建会话</el-button>
      </div>
    </header>

    <div v-if="store.demoMode" class="demo-mode-hint" role="status">
      <strong>演示模式</strong><span>已聚焦核心学习链路，按 Esc 可随时退出。</span>
    </div>

    <nav ref="flowRail" class="flow-rail" aria-label="智能学习闭环：学习画像、路径规划、资源生成、专家审校、效果评估、动态调整">
      <button
        v-for="(item, index) in flowItems"
        :key="item.key"
        :class="{'is-active': activeLoopKey === item.key, 'is-done': item.done, 'is-partial': item.partial, 'is-failed': item.failed}"
        @click="activeTab = item.tab"
      >
        <span>{{ index + 1 }}</span><strong>{{ item.label }}</strong><small>{{ item.caption }}</small>
      </button>
    </nav>

    <StatusBanner v-if="store.notice" status="error" :message="store.notice" />

    <el-tabs v-model="activeTab" class="workspace-tabs">
      <el-tab-pane name="profile" label="学习画像工作区">
        <div class="workspace-grid workspace-grid--profile">
          <ConversationPanel />
          <ProfilePanel :profile="store.profile" :previous-profile="store.previousProfile" :meta="store.profileMeta" :status="store.profileStatus" />
        </div>
      </el-tab-pane>
      <el-tab-pane name="path" label="个性化学习路径工作区">
        <LearningPathPanel
          :model-value="store.selectedStep"
          :path="store.path"
          :status="store.pathStatus"
          @update:model-value="store.selectStep"
          @retry="store.generatePath()"
        />
      </el-tab-pane>
      <el-tab-pane name="resources" label="资源中心与学习评价">
        <div class="workspace-grid workspace-grid--resources">
          <ResourceCenter
            :resources="store.resources"
            :failures="store.resourceFailures"
            :status="store.resourceStatus"
            :can-generate="store.hasCoreContext"
            :fallback-mode="fallbackModeMessage"
            @generate="store.startGeneration(true)"
          />
          <div class="progress-stack">
            <TaskProgressTimeline
              :timeline="store.taskTimeline"
              :task-status="store.task?.status ?? null"
              :connection-status="store.sseConnectionStatus"
              @retry="store.startGeneration(true)"
            />
            <AgentTracePanel v-if="!store.demoMode" class="developer-only" :traces="store.traces" :task-events="store.taskEvents" />
          </div>
          <EvaluationPanel
            :quiz="store.quiz"
            :result="store.evaluation"
            :status="store.evaluationStatus"
            :profile="store.profile"
            :previous-profile="store.previousProfile"
            :path="store.path"
            :previous-path="store.previousPath"
            @submit="store.submitEvaluation"
          />
        </div>
      </el-tab-pane>
    </el-tabs>

    <ApiIssuePanel v-if="!store.demoMode" class="developer-only" :issues="store.apiIssues" />
  </main>
</template>

<script setup lang="ts">
import {computed, nextTick, onBeforeUnmount, onMounted, ref, watch} from 'vue';
import {ElMessage} from 'element-plus';
import {Connection, CopyDocument, Monitor, RefreshLeft} from '@element-plus/icons-vue';
import AgentTracePanel from '@/components/agents/AgentTracePanel.vue';
import TaskProgressTimeline from '@/components/agents/TaskProgressTimeline.vue';
import ApiIssuePanel from '@/components/common/ApiIssuePanel.vue';
import StatusBanner from '@/components/common/StatusBanner.vue';
import EvaluationPanel from '@/components/evaluation/EvaluationPanel.vue';
import LearningPathPanel from '@/components/path/LearningPathPanel.vue';
import ConversationPanel from '@/components/profile/ConversationPanel.vue';
import ProfilePanel from '@/components/profile/ProfilePanel.vue';
import ResourceCenter from '@/components/resources/ResourceCenter.vue';
import {useLearningStore} from '@/stores/learning';
import {buildLearningPlanMarkdown, fallbackLabel, shouldExitDemoMode} from '@/utils/presentation';

const store = useLearningStore();
const activeTab = ref('profile');
const flowRail = ref<HTMLElement | null>(null);
const canCopyPlan = computed(() => Boolean(store.profile || store.path));
const fallbackModeMessage = computed(() => {
  const profileFallback = fallbackLabel(store.profileMeta?.extraction_mode);
  const pathFallback = fallbackLabel(store.path?.generation_mode);
  if (!profileFallback && !pathFallback) return null;
  return `当前资源基于含降级结果的上游上下文：${[profileFallback && '画像', pathFallback && '路径'].filter(Boolean).join('、')}。资源本身仍按 Reviewer 状态展示。`;
});
const adjustmentCompleted = computed(() => Boolean(
  store.evaluation && (
    (store.previousProfile && store.profile && store.previousProfile.version !== store.profile.version)
    || (store.previousPath && store.path && store.previousPath.path_id !== store.path.path_id)
  ),
));
const activeLoopKey = computed(() => {
  if (adjustmentCompleted.value) return 'adjustment';
  if (store.evaluation || store.resources.length) return 'evaluation';
  const reviewStage = store.taskTimeline.find((stage) => stage.key === 'review');
  if (reviewStage?.status === 'running') return 'review';
  if (store.task) return 'resources';
  if (store.path) return 'resources';
  if (store.profile) return 'path';
  return 'profile';
});
const flowItems = computed(() => [
  {key: 'profile', tab: 'profile', label: '学习画像', caption: store.profile ? `Profile v${store.profile.version}` : '理解学习需求', done: Boolean(store.profile), partial: false, failed: false},
  {key: 'path', tab: 'path', label: '路径规划', caption: store.path ? `${store.path.steps.length} 个学习步骤` : '个性化规划', done: Boolean(store.path), partial: false, failed: store.pathStatus === 'error'},
  {key: 'resources', tab: 'resources', label: '资源生成', caption: store.resources.length ? `${store.resources.length}/5 类可用` : 'RAG + 五资源', done: store.resourceStatus === 'success', partial: store.resourceStatus === 'partial', failed: store.resourceStatus === 'error'},
  {key: 'review', tab: 'resources', label: '专家审校', caption: 'Reviewer 质量检查', done: store.resources.length > 0 && store.resources.every((resource) => resource.review_status === 'approved') && store.resourceStatus === 'success', partial: store.resourceStatus === 'partial', failed: store.resourceStatus === 'error'},
  {key: 'evaluation', tab: 'resources', label: '效果评估', caption: store.evaluation ? `${Math.round(store.evaluation.mastery_score * 100)} 分` : '提交 Quiz 评价', done: Boolean(store.evaluation), partial: false, failed: store.evaluationStatus === 'error'},
  {key: 'adjustment', tab: 'resources', label: '动态调整', caption: adjustmentCompleted.value ? '画像与路径已更新' : 'Profile v2 + 新路径', done: adjustmentCompleted.value, partial: false, failed: false},
]);

async function copyLearningPlan() {
  const markdown = buildLearningPlanMarkdown(store.profile, store.path, store.resources, store.evaluation);
  if (!markdown.trim()) return;
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(markdown);
    } else {
      const textarea = document.createElement('textarea');
      textarea.value = markdown;
      textarea.setAttribute('readonly', '');
      textarea.style.position = 'fixed';
      textarea.style.opacity = '0';
      document.body.appendChild(textarea);
      textarea.select();
      const copied = document.execCommand?.('copy') ?? false;
      textarea.remove();
      if (!copied) throw new Error('clipboard unavailable');
    }
    ElMessage.success('学习方案已复制为 Markdown');
  } catch {
    ElMessage.warning('当前浏览器无法访问剪贴板，请使用支持 Clipboard API 的安全页面。');
  }
}

function handleEscape(event: KeyboardEvent) {
  if (shouldExitDemoMode(event.key, store.demoMode)) store.setDemoMode(false);
}

watch(activeLoopKey, async () => {
  await nextTick();
  flowRail.value?.querySelector<HTMLElement>('.is-active')?.scrollIntoView({block: 'nearest', inline: 'center'});
});

onMounted(() => {
  void store.checkHealth();
  window.addEventListener('keydown', handleEscape);
});
onBeforeUnmount(() => window.removeEventListener('keydown', handleEscape));
</script>
