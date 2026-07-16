<template>
  <main class="app-shell">
    <header class="app-header">
      <div class="brand-block">
        <div class="brand-mark">EA</div>
        <div><p>中国软件杯 A3 赛题</p><h1>EduAgent 学习工作台</h1></div>
      </div>
      <div class="header-actions">
        <el-tag v-if="store.developmentMode" type="warning" effect="plain">开发适配器结果</el-tag>
        <div class="health-chip" :class="`health-chip--${store.healthStatus}`"><span />{{ store.healthMessage }}</div>
        <el-button :icon="Connection" :loading="store.healthStatus === 'loading'" @click="store.checkHealth">检查连接</el-button>
        <el-button :icon="RefreshLeft" @click="store.resetSession">新建会话</el-button>
      </div>
    </header>

    <nav class="flow-rail" aria-label="核心学习流程">
      <button v-for="(item, index) in flowItems" :key="item.name" :class="{'is-active': activeTab === item.name, 'is-done': item.done}" @click="activeTab = item.name">
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
        />
      </el-tab-pane>
      <el-tab-pane name="resources" label="资源中心与学习评价">
        <div class="workspace-grid workspace-grid--resources">
          <ResourceCenter
            :resources="store.resources"
            :failures="store.resourceFailures"
            :status="store.resourceStatus"
            :can-generate="store.hasCoreContext"
            @generate="store.startGeneration(true)"
          />
          <AgentTracePanel :traces="store.traces" :task-events="store.taskEvents" />
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

    <ApiIssuePanel :issues="store.apiIssues" />
  </main>
</template>

<script setup lang="ts">
import {computed, onMounted, ref} from 'vue';
import {Connection, RefreshLeft} from '@element-plus/icons-vue';
import AgentTracePanel from '@/components/agents/AgentTracePanel.vue';
import ApiIssuePanel from '@/components/common/ApiIssuePanel.vue';
import StatusBanner from '@/components/common/StatusBanner.vue';
import EvaluationPanel from '@/components/evaluation/EvaluationPanel.vue';
import LearningPathPanel from '@/components/path/LearningPathPanel.vue';
import ConversationPanel from '@/components/profile/ConversationPanel.vue';
import ProfilePanel from '@/components/profile/ProfilePanel.vue';
import ResourceCenter from '@/components/resources/ResourceCenter.vue';
import {useLearningStore} from '@/stores/learning';

const store = useLearningStore();
const activeTab = ref('profile');
const flowItems = computed(() => [
  {name: 'profile', label: '对话与画像', caption: store.profile ? `画像 v${store.profile.version}` : '等待开始', done: Boolean(store.profile)},
  {name: 'path', label: '学习路径', caption: store.path ? `${store.path.steps.length} 个步骤` : '等待画像', done: Boolean(store.path)},
  {name: 'resources', label: '资源与评价', caption: store.resources.length ? `${store.resources.length} 类资源` : '等待路径', done: store.resources.length >= 5},
]);

onMounted(() => void store.checkHealth());
</script>
