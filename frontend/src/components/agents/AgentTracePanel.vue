<template>
  <section class="workspace-panel agent-panel">
    <div class="panel-title-row">
      <div><p class="section-kicker">多智能体协作</p><h2>生成轨迹</h2></div>
      <el-progress :percentage="progress" :stroke-width="7" />
    </div>
    <div class="agent-list">
      <article v-for="trace in traces" :key="trace.key" class="agent-row" :class="`agent-row--${trace.status}`">
        <div class="agent-state-icon">
          <el-icon v-if="trace.status === 'running'" class="is-loading"><Loading /></el-icon>
          <el-icon v-else-if="trace.status === 'completed'"><CircleCheckFilled /></el-icon>
          <el-icon v-else-if="trace.status === 'failed'"><CircleCloseFilled /></el-icon>
          <span v-else />
        </div>
        <div class="agent-copy"><strong>{{ trace.name }}</strong><span>{{ trace.label }}</span><p>{{ trace.message }}</p></div>
        <el-tag size="small" :type="tagType(trace.status)" effect="plain">{{ statusLabel[trace.status] }}</el-tag>
      </article>
    </div>
    <div v-if="taskEvents.length" class="event-counter">已接收 {{ taskEvents.length }} 条持久化 SSE 事件，按 sequence 去重。</div>
  </section>
</template>

<script setup lang="ts">
import {computed} from 'vue';
import {CircleCheckFilled, CircleCloseFilled, Loading} from '@element-plus/icons-vue';
import type {TaskEvent, UiAgentStatus, UiAgentTrace} from '@/types/api';

const props = defineProps<{traces: UiAgentTrace[]; taskEvents: TaskEvent[]}>();
const progress = computed(() => Math.max(0, ...props.traces.map((trace) => trace.progress)));
const statusLabel: Record<UiAgentStatus, string> = {waiting: '等待中', running: '运行中', completed: '已完成', failed: '失败'};
function tagType(status: UiAgentStatus) { return ({running: 'primary', completed: 'success', failed: 'danger', waiting: 'info'} as const)[status]; }
</script>
