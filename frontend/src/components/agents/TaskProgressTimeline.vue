<template>
  <section class="workspace-panel task-timeline-panel" aria-labelledby="task-progress-title">
    <div class="panel-title-row">
      <div>
        <p class="section-kicker">学习方案生成进度</p>
        <h2 id="task-progress-title">课程知识与资源处理</h2>
      </div>
      <el-tag :type="terminalTagType" effect="plain">{{ terminalLabel }}</el-tag>
    </div>

    <div v-if="connectionMessage" class="stream-state" :class="`stream-state--${connectionStatus}`" role="status">
      <span class="stream-state__dot" />
      {{ connectionMessage }}
    </div>

    <ol class="task-timeline">
      <li v-for="stage in timeline" :key="stage.key" :class="`timeline-stage timeline-stage--${stage.status}`">
        <div class="timeline-stage__marker" aria-hidden="true">
          <el-icon v-if="stage.status === 'running'" class="is-loading"><Loading /></el-icon>
          <el-icon v-else-if="stage.status === 'completed'"><Check /></el-icon>
          <el-icon v-else-if="stage.status === 'partial'"><Warning /></el-icon>
          <el-icon v-else-if="stage.status === 'failed'"><Close /></el-icon>
          <span v-else />
        </div>
        <div class="timeline-stage__body">
          <div class="timeline-stage__heading">
            <strong>{{ stage.label }}</strong>
          </div>
          <p>{{ stage.description }}</p>
          <div v-if="stage.resources" class="resource-stage-grid" aria-label="五类资源生成状态">
            <span v-for="resource in stage.resources" :key="resource.key" :class="`resource-stage-chip resource-stage-chip--${resource.status}`">
              <i aria-hidden="true" />{{ resource.label }}
            </span>
          </div>
        </div>
      </li>
    </ol>

    <el-button v-if="taskStatus === 'failed'" class="timeline-retry" type="primary" plain @click="$emit('retry')">
      重新生成资源
    </el-button>
  </section>
</template>

<script setup lang="ts">
import {computed} from 'vue';
import {Check, Close, Loading, Warning} from '@element-plus/icons-vue';
import type {StreamConnectionStatus} from '@/api/sse';
import type {TaskStatus} from '@/types/api';
import type {TimelineStage} from '@/utils/presentation';

const props = defineProps<{
  timeline: TimelineStage[];
  taskStatus: TaskStatus | null;
  connectionStatus: StreamConnectionStatus | 'idle';
}>();
defineEmits<{(event: 'retry'): void}>();

const terminalLabel = computed(() => ({
  completed: '全部完成', partial_success: '部分完成', failed: '生成失败', running: '进行中', pending: '等待中',
}[props.taskStatus ?? 'pending']));
const terminalTagType = computed(() => ({
  completed: 'success', partial_success: 'warning', failed: 'danger', running: 'primary', pending: 'info',
} as const)[props.taskStatus ?? 'pending']);
const connectionMessage = computed(() => ({
  idle: '', connecting: '正在连接任务进度', connected: 'SSE 实时进度已连接',
  reconnecting: '进度连接短暂中断，正在自动重连', disconnected: '实时连接已中断，任务状态轮询仍在继续', closed: '',
}[props.connectionStatus]));
</script>
