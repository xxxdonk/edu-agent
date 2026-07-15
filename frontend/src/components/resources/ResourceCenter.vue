<template>
  <section class="workspace-panel resource-center">
    <div class="panel-title-row">
      <div><p class="section-kicker">资源中心</p><h2>五类个性化学习资源</h2></div>
      <el-button type="primary" :icon="MagicStick" :loading="status === 'loading'" :disabled="!canGenerate" @click="$emit('generate')">
        {{ resources.length ? '重试生成' : '生成五类资源' }}
      </el-button>
    </div>
    <StatusBanner v-if="status === 'loading'" status="loading" message="Orchestrator 正在并行调度资源 Agent，请查看右侧生成轨迹" />
    <StatusBanner v-else-if="status === 'partial'" status="partial" message="部分资源生成失败，成功资源仍可正常查看和评价" />
    <StatusBanner v-else-if="status === 'error'" status="error" message="本次没有获得可用资源，请保留画像和路径后重试生成" />
    <div v-if="failures.length" class="resource-errors">
      <p v-for="(failure, index) in failures" :key="index">{{ failure }}</p>
    </div>
    <el-empty v-if="!resources.length && status !== 'loading'" description="选择路径步骤后生成课程讲解、思维导图、练习、阅读和代码" />
    <div v-else-if="resources.length" class="resource-layout">
      <nav class="resource-nav" aria-label="学习资源列表">
        <button v-for="resource in sortedResources" :key="resource.resource_id" type="button" :class="{'is-active': selectedId === resource.resource_id}" @click="selectedId = resource.resource_id">
          <component :is="resourceIcon(resource.resource_type)" />
          <span><small>{{ typeLabel[resource.resource_type] }}</small><strong>{{ resource.title }}</strong></span>
          <el-tag size="small" :type="reviewType(resource.review_status)" effect="plain">{{ reviewLabel[resource.review_status] }}</el-tag>
        </button>
      </nav>
      <article v-if="selectedResource" class="resource-detail">
        <div class="resource-heading">
          <div><p>{{ typeLabel[selectedResource.resource_type] }}</p><h3>{{ selectedResource.title }}</h3></div>
          <el-tag>{{ difficultyLabel[selectedResource.difficulty] }}</el-tag>
        </div>
        <dl class="resource-metadata">
          <div><dt>目标知识点</dt><dd>{{ selectedResource.target_topic }}</dd></div>
          <div><dt>个性化原因</dt><dd>{{ selectedResource.personalization_reason }}</dd></div>
          <div><dt>内容来源</dt><dd>{{ selectedResource.source_references.map((item) => item.title).join('、') }}</dd></div>
          <div><dt>审校状态</dt><dd>{{ reviewLabel[selectedResource.review_status] }}</dd></div>
          <div><dt>创建时间</dt><dd>{{ formatDate(selectedResource.created_at) }}</dd></div>
        </dl>
        <el-collapse class="source-collapse">
          <el-collapse-item title="查看知识库来源与定位">
            <div v-for="source in selectedResource.source_references" :key="`${source.source_id}-${source.locator}`" class="source-row">
              <strong>{{ source.title }}</strong><code>{{ source.locator }}</code><span v-if="source.chunk_id">{{ source.chunk_id }}</span>
            </div>
          </el-collapse-item>
        </el-collapse>
        <ResourcePreview :resource="selectedResource" />
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import {computed, ref, watch} from 'vue';
import {Collection, DataAnalysis, Document, MagicStick, Notebook, Tickets} from '@element-plus/icons-vue';
import ResourcePreview from './ResourcePreview.vue';
import StatusBanner from '@/components/common/StatusBanner.vue';
import type {Difficulty, Resource, ResourceType, ReviewStatus, ViewStatus} from '@/types/api';

const props = defineProps<{resources: Resource[]; failures: string[]; status: ViewStatus; canGenerate: boolean}>();
defineEmits<{(event: 'generate'): void}>();
const selectedId = ref('');
const order: ResourceType[] = ['explanation', 'mind_map', 'quiz', 'reading', 'coding'];
const sortedResources = computed(() => [...props.resources].sort((a, b) => order.indexOf(a.resource_type) - order.indexOf(b.resource_type)));
const selectedResource = computed(() => sortedResources.value.find((item) => item.resource_id === selectedId.value) ?? sortedResources.value[0]);
watch(() => props.resources, (resources) => { if (!resources.some((item) => item.resource_id === selectedId.value)) selectedId.value = resources[0]?.resource_id ?? ''; }, {immediate: true});

const typeLabel: Record<ResourceType, string> = {explanation: 'Markdown 课程讲解', mind_map: 'Mermaid 思维导图', quiz: '分层练习题', reading: '拓展阅读', coding: 'Python 代码实践'};
const reviewLabel: Record<ReviewStatus, string> = {pending: '待审校', approved: '审校通过', rejected: '未通过', needs_revision: '需修改'};
const difficultyLabel: Record<Difficulty, string> = {beginner: '入门', intermediate: '中级', advanced: '高级'};
function reviewType(status: ReviewStatus) { return ({pending: 'info', approved: 'success', rejected: 'danger', needs_revision: 'warning'} as const)[status]; }
function resourceIcon(type: ResourceType) { return ({explanation: Document, mind_map: DataAnalysis, quiz: Tickets, reading: Collection, coding: Notebook})[type]; }
function formatDate(value: string) { return new Intl.DateTimeFormat('zh-CN', {dateStyle: 'medium', timeStyle: 'short'}).format(new Date(value)); }
</script>
