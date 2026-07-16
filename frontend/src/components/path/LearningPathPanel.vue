<template>
  <section class="workspace-panel path-panel">
    <div class="panel-title-row">
      <div>
        <p class="section-kicker">个性化学习路径</p>
        <h2>{{ path?.course || '等待画像生成' }}</h2>
      </div>
      <div class="path-summary" v-if="path">
        <strong>{{ totalMinutes }}</strong><span>分钟</span>
        <strong>{{ path.steps.length }}</strong><span>步骤</span>
      </div>
    </div>
    <StatusBanner v-if="status === 'loading'" status="loading" message="Planner Agent 正在安排主题顺序与完成标准" />
    <el-empty v-else-if="!path" description="学习路径将在画像生成后自动规划" />
    <template v-else>
      <div class="path-meta">
        <el-tag :type="path.generation_mode === 'llm_structured' ? 'success' : 'warning'" effect="plain">
          {{ path.generation_mode === 'llm_structured' ? '结构化大模型结果' : '开发适配器结果' }}
        </el-tag>
        <span>基于画像 v{{ path.profile_version }}</span>
        <span v-if="path.adjustment_reason">调整原因：{{ path.adjustment_reason }}</span>
      </div>
      <div class="learning-timeline">
        <article v-for="step in sortedSteps" :key="step.step" class="learning-step" :class="{'learning-step--active': modelValue === step.step}" @click="$emit('update:modelValue', step.step)">
          <div class="step-marker"><span>{{ step.step }}</span></div>
          <div class="step-content">
            <div class="step-title-row">
              <div><p>学习主题</p><h3>{{ step.topic }}</h3></div>
              <el-tag :type="modelValue === step.step ? 'primary' : 'info'">{{ modelValue === step.step ? '当前步骤' : '未开始' }}</el-tag>
            </div>
            <div class="step-facts">
              <div><span>学习目标</span><p>{{ step.learning_goal }}</p></div>
              <div><span>安排原因</span><p>{{ step.reason }}</p></div>
              <div><span>前置知识</span><p>{{ step.prerequisites.join('、') || '无' }}</p></div>
              <div><span>预计时间</span><p>{{ step.estimated_minutes }} 分钟</p></div>
              <div><span>推荐资源</span><p>{{ step.recommended_resources.map(resourceLabel).join('、') }}</p></div>
              <div><span>完成标准</span><p>{{ step.completion_criteria.join('；') }}</p></div>
            </div>
          </div>
        </article>
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import {computed} from 'vue';
import StatusBanner from '@/components/common/StatusBanner.vue';
import type {LearningPath, ResourceType, ViewStatus} from '@/types/api';

const props = defineProps<{path: LearningPath | null; status: ViewStatus; modelValue: number}>();
defineEmits<{(event: 'update:modelValue', value: number): void}>();
const sortedSteps = computed(() => [...(props.path?.steps ?? [])].sort((a, b) => a.step - b.step));
const totalMinutes = computed(() => sortedSteps.value.reduce((sum, step) => sum + step.estimated_minutes, 0));
const resourceLabels: Record<ResourceType, string> = {explanation: '课程讲解', mind_map: '思维导图', quiz: '分层练习', reading: '拓展阅读', coding: '代码实践'};
function resourceLabel(type: ResourceType) { return resourceLabels[type]; }
</script>
