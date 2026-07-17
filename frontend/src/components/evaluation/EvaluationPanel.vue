<template>
  <section class="workspace-panel evaluation-panel">
    <div class="panel-title-row">
      <div><p class="section-kicker">学习评价</p><h2>练习、反馈与动态调整</h2></div>
      <el-tag v-if="quiz" effect="plain">{{ quiz.questions.length }} 题 · {{ quiz.topic }}</el-tag>
    </div>
    <el-empty v-if="!quiz" description="生成分层练习题后可提交学习评价" />
    <template v-else>
      <div class="quiz-list">
        <article v-for="(question, index) in quiz.questions" :key="question.id" class="quiz-question">
          <div class="question-number">{{ index + 1 }}</div>
          <div class="question-body">
            <div class="question-meta"><el-tag size="small">{{ levelLabel(question.level) }}</el-tag><span>{{ typeLabel(question.type) }}</span></div>
            <h3>{{ question.question }}</h3>
            <el-radio-group v-if="question.options?.length" v-model="answers[question.id]" class="option-group">
              <el-radio v-for="option in question.options" :key="option" :value="option.slice(0, 1)">{{ option }}</el-radio>
            </el-radio-group>
            <el-input v-else v-model="answers[question.id]" type="textarea" :rows="3" placeholder="请输入你的回答" />
            <div v-if="result" class="answer-review" :class="`answer-review--${questionResult(question.id).status}`">
              <strong>{{ questionResult(question.id).line || '已完成评价' }}</strong>
              <p>参考答案：{{ question.answer }}</p>
              <p>解析：{{ question.explanation }}</p>
            </div>
          </div>
        </article>
      </div>
      <div class="evaluation-actions">
        <label>用时 <el-input-number v-model="timeSpent" :min="0" :max="600" /> 分钟</label>
        <el-button type="primary" :icon="Checked" :loading="status === 'loading'" :disabled="!allAnswered" @click="$emit('submit', answers, timeSpent)">提交评价</el-button>
      </div>
      <StatusBanner v-if="status === 'error'" status="error" message="评价没有成功，当前答案仍保留在页面中" />
      <div v-if="result" class="evaluation-result">
        <div class="score-block" :class="{'score-block--passed': result.passed}">
          <div><strong>{{ Math.round(result.mastery_score * 100) }}</strong><span>总分 / 100</span></div>
          <el-tag :type="result.passed ? 'success' : 'warning'" size="large">{{ result.passed ? '已通过' : '需巩固' }}</el-tag>
        </div>
        <div class="feedback-grid">
          <div><h4>薄弱知识点</h4><p>{{ result.weak_topics.join('、') || '本轮未发现明显薄弱点' }}</p></div>
          <div><h4>学习建议</h4><p>{{ suggestion }}</p></div>
        </div>
        <pre class="feedback-text">{{ result.feedback }}</pre>
        <DiffComparison title="画像更新前后" :rows="profileRows" empty-text="本轮评价未改变画像字段" />
        <DiffComparison title="路径更新前后" :rows="pathRows" empty-text="本轮评价未调整学习路径" />
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import {computed, reactive, ref, watch} from 'vue';
import {Checked} from '@element-plus/icons-vue';
import DiffComparison from './DiffComparison.vue';
import StatusBanner from '@/components/common/StatusBanner.vue';
import {evaluationQuestionFeedback, pathDiff, profileDiff} from '@/utils/content';
import type {EvaluationResult, LearningPath, QuizDocument, StudentProfile, ViewStatus} from '@/types/api';

const props = defineProps<{
  quiz: QuizDocument | null; result: EvaluationResult | null; status: ViewStatus;
  profile: StudentProfile | null; previousProfile: StudentProfile | null;
  path: LearningPath | null; previousPath: LearningPath | null;
}>();
defineEmits<{(event: 'submit', answers: Record<string, string>, minutes: number): void}>();
const answers = reactive<Record<string, string>>({});
const timeSpent = ref(12);
const allAnswered = computed(() => props.quiz?.questions.every((question) => answers[question.id]?.trim()) ?? false);
const quizFingerprint = computed(() => JSON.stringify(
  props.quiz?.questions.map((question) => ({id: question.id, question: question.question, options: question.options})) ?? [],
));
const profileRows = computed(() => profileDiff(props.previousProfile, props.profile));
const pathRows = computed(() => pathDiff(props.previousPath, props.path));
const suggestion = computed(() => props.result?.passed ? '进入学习路径的下一步骤，并用代码实践巩固当前主题。' : `优先复习${props.result?.weak_topics.join('、') || '当前主题'}，完成讲解与代码资源后再次练习。`);

watch(quizFingerprint, () => {
  Object.keys(answers).forEach((key) => delete answers[key]);
  timeSpent.value = 12;
});
function levelLabel(level: string) { return ({basic: '基础', intermediate: '进阶', advanced: '挑战'} as Record<string, string>)[level] ?? level; }
function typeLabel(type: string) { return ({single_choice: '单选题', short_answer: '简答题', comprehensive: '综合题'} as Record<string, string>)[type] ?? type; }
function questionResult(questionId: string) { return evaluationQuestionFeedback(props.result?.feedback ?? '', questionId); }
</script>
