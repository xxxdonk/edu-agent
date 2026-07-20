<template>
  <section class="workspace-panel profile-panel">
    <div class="panel-title-row">
      <div>
        <p class="section-kicker">动态学习画像</p>
        <h2>{{ profile ? `画像 v${profile.version}` : '等待对话生成' }}</h2>
      </div>
      <el-progress v-if="profile" type="circle" :width="54" :stroke-width="5" :percentage="Math.round(profile.confidence * 100)" />
    </div>

    <StatusBanner v-if="status === 'loading'" status="loading" message="正在分析画像：识别字段 → 核验对话证据 → 计算置信度" />
    <el-empty v-else-if="!profile" description="完成一轮自然语言对话后生成画像" :image-size="88" />
    <template v-else>
      <div class="profile-meta">
        <el-tag :type="meta?.is_complete ? 'success' : 'warning'">{{ meta?.is_complete ? '画像信息完整' : '仍需补充信息' }}</el-tag>
        <el-tag v-if="modeLabel" :type="meta?.extraction_mode === 'llm_structured' ? 'success' : 'warning'" effect="plain">{{ modeLabel }}</el-tag>
        <span>更新于 {{ formatDate(profile.updated_at) }}</span>
      </div>
      <StatusBanner
        v-if="meta?.extraction_mode === 'development_heuristic'"
        status="partial"
        message="本轮使用开发降级结果，不代表结构化模型成功；已有画像仍可继续学习流程。"
      />
      <div v-if="meta?.missing_dimensions.length" class="missing-line">
        待补充：{{ meta.missing_dimensions.map(labelForKey).join('、') }}
      </div>
      <div class="profile-grid">
        <article
          v-for="dimension in dimensions"
          :key="dimension.key"
          class="profile-dimension"
          :class="`profile-dimension--${fieldState(dimension.field)}`"
        >
          <div class="profile-dimension__head">
            <span>{{ dimension.label }}</span>
            <span class="profile-field-state">{{ fieldStateLabel(dimension.field) }}</span>
            <strong>{{ Math.round(dimension.field.confidence * 100) }}%</strong>
          </div>
          <div class="profile-dimension__value">{{ formatValue(dimension.field.value) }}</div>
          <el-popover placement="bottom-start" :width="340" trigger="click">
            <template #reference>
              <button class="evidence-button" type="button"><el-icon><DocumentChecked /></el-icon> 查看字段证据</button>
            </template>
            <div v-if="dimension.field.evidence.length" class="evidence-list">
              <div v-for="(evidence, index) in dimension.field.evidence" :key="index">
                <el-tag size="small" effect="plain">{{ evidenceSourceLabel[evidence.source] }}</el-tag>
                <p>{{ evidence.quote }}</p>
              </div>
            </div>
            <p v-else class="muted-text">该字段暂无直接证据。</p>
          </el-popover>
        </article>
      </div>
      <div v-if="previousProfile && previousProfile.version !== profile.version" class="update-note">
        <el-icon><Refresh /></el-icon>
        画像已从 v{{ previousProfile.version }} 更新为 v{{ profile.version }}，历史版本仍由后端保存。
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import {computed} from 'vue';
import {DocumentChecked, Refresh} from '@element-plus/icons-vue';
import StatusBanner from '@/components/common/StatusBanner.vue';
import type {EvidenceSource, ProfileChatResponse, ProfileField, StudentProfile, ViewStatus} from '@/types/api';

const props = defineProps<{
  profile: StudentProfile | null;
  previousProfile: StudentProfile | null;
  meta: Pick<ProfileChatResponse, 'missing_dimensions' | 'next_question' | 'is_complete' | 'extraction_mode'> | null;
  status: ViewStatus;
}>();

const evidenceSourceLabel: Record<EvidenceSource, string> = {
  conversation: '对话原文', evaluation: '学习评价', inference: '模型推断', system_default: '系统默认',
};
const labels: Record<string, string> = {
  major: '学习阶段/专业', course: '当前课程', knowledge_level: '知识水平', learning_goals: '学习目标',
  weak_topics: '薄弱知识点', learning_history: '学习历史', cognitive_style: '认知风格',
  language_preference: '语言偏好', resource_preference: '资源偏好', time_budget: '可用学习时间',
};

const dimensions = computed(() => {
  if (!props.profile) return [];
  return Object.entries(labels).map(([key, label]) => ({
    key, label, field: props.profile?.[key as keyof StudentProfile] as ProfileField<unknown>,
  }));
});
const modeLabel = computed(() => props.meta?.extraction_mode === 'llm_structured' ? '结构化大模型结果' : props.meta ? '开发适配器结果' : '');

function labelForKey(key: string) { return labels[key] ?? key; }
function hasValue(value: unknown) {
  return value !== null && value !== undefined && value !== '' && (!Array.isArray(value) || value.length > 0);
}
function fieldState(field: ProfileField<unknown>) {
  if (!hasValue(field.value)) return 'missing';
  return field.confidence < 0.65 ? 'low' : 'recognized';
}
function fieldStateLabel(field: ProfileField<unknown>) {
  return ({missing: '信息不足', low: '待确认', recognized: '已理解'} as const)[fieldState(field)];
}
function formatDate(value: string) { return new Intl.DateTimeFormat('zh-CN', {month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit'}).format(new Date(value)); }
function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '信息不足';
  if (Array.isArray(value)) return value.length ? value.join('、') : '信息不足';
  if (typeof value === 'object') {
    const budget = value as {minutes_per_day?: number; days_per_week?: number};
    return `每天 ${budget.minutes_per_day ?? 0} 分钟 · 每周 ${budget.days_per_week ?? 0} 天`;
  }
  const map: Record<string, string> = {beginner: '入门', intermediate: '中级', advanced: '高级', practice_oriented: '实践导向'};
  return map[String(value)] ?? String(value);
}
</script>
