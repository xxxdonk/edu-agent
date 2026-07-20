<template>
  <section class="workspace-panel resource-center">
    <div class="panel-title-row">
      <div><p class="section-kicker">资源中心</p><h2>五类个性化学习资源</h2></div>
      <el-button
        type="primary"
        :icon="MagicStick"
        :loading="status === 'loading'"
        :disabled="!canGenerate"
        :title="canGenerate ? '为当前路径步骤生成五类资源' : '请先生成画像和学习路径'"
        @click="$emit('generate')"
      >
        {{ resources.length ? '重试生成' : '生成五类资源' }}
      </el-button>
    </div>
    <section class="resource-package" aria-labelledby="resource-package-title">
      <div class="resource-package__heading">
        <div><p class="section-kicker">学习闭环</p><h3 id="resource-package-title">本次学习资源包</h3></div>
        <el-tag :type="packageSummary.partial ? 'warning' : (packageSummary.completed === 5 ? 'success' : 'info')" effect="plain">
          {{ packageSummary.completed }}/5 类可用
        </el-tag>
      </div>
      <dl class="resource-package__facts">
        <div><dt>学习主题</dt><dd>{{ packageSummary.topic }}</dd></div>
        <div><dt>当前难度</dt><dd>{{ packageDifficulty }}</dd></div>
        <div><dt>RAG 来源</dt><dd>{{ packageSummary.sourceCount }} 项</dd></div>
        <div><dt>Reviewer</dt><dd>{{ packageSummary.approvedCount }}/{{ resources.length }} 项通过</dd></div>
        <div><dt>Evaluation</dt><dd>{{ packageSummary.evaluationLabel }}</dd></div>
        <div v-if="packageSummary.estimatedMinutes !== null"><dt>本步骤时间预算</dt><dd>{{ packageSummary.estimatedMinutes }} 分钟</dd></div>
      </dl>
      <div class="learning-sequence" aria-label="推荐学习顺序">
        <span v-for="(label, index) in packageSummary.recommendedOrder" :key="label" :class="{'is-ready': index < packageSummary.completed}">
          <b>{{ index + 1 }}</b>{{ label === '代码实践' ? practiceLabel : label }}
        </span>
      </div>
      <StatusBanner
        v-if="packageSummary.partial"
        status="partial"
        :message="`资源包部分完成，暂缺：${packageSummary.missingLabels.join('、')}。已完成资源仍可继续学习。`"
      />
    </section>
    <StatusBanner v-if="status === 'loading'" status="loading" message="正在检索知识库并并行生成五类资源，随后逐项进入 Reviewer 审校" />
    <StatusBanner v-else-if="status === 'partial'" status="partial" message="任务部分完成：成功资源可继续使用，失败项可单独查看后整体重试。" action-label="重试失败项" @action="$emit('generate')" />
    <StatusBanner v-else-if="status === 'error'" status="error" message="本次没有获得可用资源，画像和路径均已保留。" action-label="重新生成" @action="$emit('generate')" />
    <StatusBanner v-if="fallbackMode" status="partial" :message="fallbackMode" />
    <div v-if="failures.length" class="resource-errors">
      <article v-for="(failure, index) in failures" :key="index">
        <strong>资源 {{ index + 1 }} 未完成</strong>
        <p>{{ safeFailureMessage(failure) }}</p>
      </article>
    </div>
    <el-empty v-if="!resources.length && status !== 'loading'" description="选择路径步骤后生成课程讲解、思维导图、练习、阅读和代码" />
    <div v-else-if="resources.length" class="resource-layout">
      <nav class="resource-nav" aria-label="学习资源列表">
        <button
          v-for="resource in sortedResources"
          :key="resource.resource_id"
          type="button"
          class="resource-nav-card"
          :class="[`resource-type--${resource.resource_type}`, {'is-active': selectedId === resource.resource_id}]"
          :aria-pressed="selectedId === resource.resource_id"
          @click="selectedId = resource.resource_id"
        >
          <component :is="resourceIcon(resource.resource_type)" />
          <span class="resource-nav-card__copy">
            <small>{{ typeLabelFor(resource) }}</small>
            <strong>{{ resource.title }}</strong>
            <em>{{ resource.target_topic }} · {{ actualRagSources(resource.source_references).length }} 个本地来源</em>
          </span>
          <span class="resource-nav-card__status">
            <el-tag size="small" type="success" effect="plain">已生成</el-tag>
            <el-tag size="small" :type="reviewType(resource.review_status)" effect="plain">{{ reviewLabel[resource.review_status] }}</el-tag>
          </span>
        </button>
      </nav>
      <article v-if="selectedResource" class="resource-detail">
        <div class="resource-heading">
          <div><p>{{ typeLabelFor(selectedResource) }}</p><h3>{{ selectedResource.title }}</h3></div>
          <div class="resource-heading__tags">
            <el-tag>{{ difficultyLabel[selectedResource.difficulty] }}</el-tag>
            <el-tag :type="reviewType(selectedResource.review_status)" effect="plain">{{ reviewLabel[selectedResource.review_status] }}</el-tag>
          </div>
        </div>
        <dl class="resource-metadata">
          <div><dt>目标知识点</dt><dd>{{ selectedResource.target_topic }}</dd></div>
          <div><dt>个性化原因</dt><dd>{{ selectedResource.personalization_reason }}</dd></div>
          <div><dt>内容来源</dt><dd>{{ sourceDescription }}</dd></div>
          <div><dt>审校状态</dt><dd>{{ reviewLabel[selectedResource.review_status] }}</dd></div>
          <div><dt>生成状态</dt><dd>已生成</dd></div>
          <div><dt>创建时间</dt><dd>{{ formatDate(selectedResource.created_at) }}</dd></div>
        </dl>
        <section v-if="personalizationEvidence.length" class="personalization-evidence">
          <h4>个性化依据</h4>
          <ul><li v-for="item in personalizationEvidence" :key="item">{{ item }}</li></ul>
        </section>
        <StatusBanner
          v-if="isDevelopmentFallback"
          status="partial"
          message="该资源由本地规则降级生成，已明确保留来源与 Reviewer 状态。"
        />
        <StatusBanner
          v-if="usesGeneralModel(selectedResource.source_references)"
          status="partial"
          message="未命中本地课程资料，使用通用模型或学科规则生成。"
        />
        <el-collapse v-if="selectedActualSources.length" class="source-collapse">
          <el-collapse-item title="查看知识库来源与定位">
            <div v-for="source in selectedActualSources" :key="`${source.source_id}-${source.locator}`" class="source-row">
              <strong>{{ source.title }}</strong><code>{{ source.locator }}</code><span v-if="source.chunk_id">{{ source.chunk_id }}</span>
            </div>
          </el-collapse-item>
        </el-collapse>
        <StatusBanner
          v-if="selectedResource.review_status === 'rejected'"
          status="error"
          message="该资源未通过 Reviewer 安全审校，内容已阻止展示，请重新生成。"
        />
        <ResourcePreview v-else :resource="selectedResource" />
        <section v-if="selectedResource.review_status !== 'rejected'" class="resource-follow-ups">
          <h4>学习追问建议</h4>
          <div>
            <el-button
              v-for="suggestion in followUpSuggestions"
              :key="suggestion"
              size="small"
              plain
              @click="$emit('follow-up', suggestion)"
            >{{ suggestion }}</el-button>
          </div>
        </section>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import {computed, ref, watch} from 'vue';
import {Collection, DataAnalysis, Document, MagicStick, Notebook, Tickets} from '@element-plus/icons-vue';
import ResourcePreview from './ResourcePreview.vue';
import StatusBanner from '@/components/common/StatusBanner.vue';
import type {Difficulty, EvaluationResult, LearningPath, Resource, ResourceType, ReviewStatus, StudentProfile, TaskState, ViewStatus} from '@/types/api';
import {formatSourceTitles} from '@/utils/content';
import {buildResourcePackageSummary, profilePersonalizationEvidence, resourceFollowUpSuggestions, safeFailureMessage} from '@/utils/presentation';
import {actualRagSources, practiceDisplayName, profileCourse, resourceDisplayName, usesGeneralModel} from '@/utils/subject';

const props = defineProps<{
  resources: Resource[]; failures: string[]; status: ViewStatus; canGenerate: boolean;
  fallbackMode?: string | null; profile: StudentProfile | null; path: LearningPath | null;
  selectedStep: number; task: TaskState | null; evaluation: EvaluationResult | null;
}>();
defineEmits<{(event: 'generate'): void; (event: 'follow-up', suggestion: string): void}>();
const selectedId = ref('');
const order: ResourceType[] = ['explanation', 'mind_map', 'reading', 'coding', 'quiz'];
const sortedResources = computed(() => [...props.resources].sort((a, b) => order.indexOf(a.resource_type) - order.indexOf(b.resource_type)));
const selectedResource = computed(() => sortedResources.value.find((item) => item.resource_id === selectedId.value) ?? sortedResources.value[0]);
const packageSummary = computed(() => buildResourcePackageSummary(props.resources, props.path, props.selectedStep, props.task, props.evaluation));
const packageDifficulty = computed(() => difficultyLabel[packageSummary.value.difficulty as Difficulty] ?? packageSummary.value.difficulty);
const personalizationEvidence = computed(() => profilePersonalizationEvidence(props.profile));
const currentCourse = computed(() => profileCourse(props.profile));
const practiceLabel = computed(() => practiceDisplayName(currentCourse.value));
const selectedActualSources = computed(() => actualRagSources(selectedResource.value?.source_references ?? []));
const sourceDescription = computed(() => selectedActualSources.value.length
  ? `${selectedActualSources.value.length} 项 · ${formatSourceTitles(selectedActualSources.value)}`
  : '未命中本地课程资料，使用通用模型');
const followUpSuggestions = computed(() => selectedResource.value ? resourceFollowUpSuggestions(selectedResource.value.resource_type) : []);
const isDevelopmentFallback = computed(() => selectedResource.value?.personalization_reason.toLowerCase().includes('development fallback') ?? false);
watch(() => props.resources, (resources) => { if (!resources.some((item) => item.resource_id === selectedId.value)) selectedId.value = resources[0]?.resource_id ?? ''; }, {immediate: true});

function typeLabelFor(resource: Resource) { return resourceDisplayName(resource, currentCourse.value); }
const reviewLabel: Record<ReviewStatus, string> = {pending: '待审校', approved: '审校通过', rejected: '未通过', needs_revision: '需修改'};
const difficultyLabel: Record<Difficulty, string> = {beginner: '入门', intermediate: '中级', advanced: '高级'};
function reviewType(status: ReviewStatus) { return ({pending: 'info', approved: 'success', rejected: 'danger', needs_revision: 'warning'} as const)[status]; }
function resourceIcon(type: ResourceType) { return ({explanation: Document, mind_map: DataAnalysis, quiz: Tickets, reading: Collection, coding: Notebook})[type]; }
function formatDate(value: string) { return new Intl.DateTimeFormat('zh-CN', {dateStyle: 'medium', timeStyle: 'short'}).format(new Date(value)); }
</script>
