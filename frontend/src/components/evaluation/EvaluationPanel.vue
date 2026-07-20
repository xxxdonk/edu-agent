<template>
  <section class="workspace-panel evaluation-panel">
    <div class="panel-title-row">
      <div><p class="section-kicker">学习评价</p><h2>练习、反馈与动态调整</h2></div>
      <el-tag v-if="quiz" effect="plain">{{ quiz.questions.length }} 题 · {{ quiz.topic }}</el-tag>
    </div>
    <el-empty v-if="!quiz" description="生成分层练习题后可提交学习评价" />
    <template v-else>
      <StatusBanner v-if="status === 'loading'" status="loading" message="正在逐题评分 → 识别薄弱知识点 → 更新画像 → 重新规划路径" />
      <StatusBanner v-else-if="status === 'error'" status="error" message="评价没有成功，当前答案仍保留在页面中。" action-label="重试评价" @action="retryEvaluation" />
      <div v-else-if="!result" class="evaluation-ready-state">
        <strong>完成题目后提交 Evaluation</strong>
        <span>系统将读取持久化标准答案评分，并展示画像与路径变化。</span>
      </div>
      <div class="quiz-progress">
        <div><strong>第 {{ currentIndex + 1 }} / {{ quiz.questions.length }} 题</strong><span>已完成 {{ answeredCount }} 题</span></div>
        <el-progress :percentage="completionPercentage" :show-text="false" />
      </div>
      <div class="quiz-question-nav" aria-label="题目导航">
        <button
          v-for="(question, index) in quiz.questions"
          :key="question.id"
          type="button"
          :class="{'is-current': index === currentIndex, 'is-answered': Boolean(answers[question.id]?.trim())}"
          :aria-label="`第 ${index + 1} 题${answers[question.id]?.trim() ? '，已作答' : '，未作答'}`"
          @click="currentIndex = index"
        >{{ index + 1 }}</button>
      </div>
      <div v-if="currentQuestion" class="quiz-list">
        <article :key="currentQuestion.id" class="quiz-question">
          <div class="question-number">{{ currentIndex + 1 }}</div>
          <div class="question-body">
            <div class="question-meta"><el-tag size="small">{{ levelLabel(currentQuestion.level) }}</el-tag><span>{{ typeLabel(currentQuestion.type) }}</span></div>
            <h3>{{ currentQuestion.question }}</h3>
            <el-radio-group v-if="currentQuestion.options?.length" v-model="answers[currentQuestion.id]" class="option-group">
              <el-radio v-for="option in currentQuestion.options" :key="option" :value="option.slice(0, 1)">{{ option }}</el-radio>
            </el-radio-group>
            <el-input v-else v-model="answers[currentQuestion.id]" type="textarea" :rows="3" placeholder="请输入你的回答" />
            <div v-if="result" class="answer-review" :class="`answer-review--${questionResult(currentQuestion.id).status}`">
              <strong>{{ questionResult(currentQuestion.id).line || '已完成评价' }}</strong>
              <p>参考答案：{{ currentQuestion.answer }}</p>
              <p>解析：{{ currentQuestion.explanation }}</p>
            </div>
          </div>
        </article>
      </div>
      <div class="quiz-navigation-actions">
        <el-button :icon="ArrowLeft" :disabled="currentIndex === 0" @click="currentIndex -= 1">上一题</el-button>
        <span>{{ unansweredCount ? `还有 ${unansweredCount} 题未作答` : '全部题目已作答' }}</span>
        <el-button :icon="ArrowRight" :disabled="currentIndex >= quiz.questions.length - 1" @click="currentIndex += 1">下一题</el-button>
      </div>
      <div class="evaluation-actions">
        <label>用时 <el-input-number v-model="timeSpent" :min="0" :max="600" /> 分钟</label>
        <el-button type="primary" :icon="Checked" :loading="status === 'loading'" :disabled="Boolean(result)" @click="submitEvaluation">{{ result ? '已提交评价' : '提交评价' }}</el-button>
      </div>
      <div v-if="result" class="evaluation-result">
        <div class="score-block" :class="{'score-block--passed': result.passed}">
          <div><strong>{{ Math.round(result.mastery_score * 100) }}</strong><span>总分 / 100</span></div>
          <el-tag :type="result.passed ? 'success' : 'warning'" size="large">{{ result.passed ? '已通过' : '需巩固' }}</el-tag>
        </div>
        <div class="feedback-grid">
          <div><h4>错题与待巩固</h4><p>{{ incorrectCount }} 题</p></div>
          <div><h4>薄弱知识点</h4><p>{{ result.weak_topics.join('、') || '本轮未发现明显薄弱点' }}</p></div>
          <div><h4>学习建议</h4><p>{{ suggestion }}</p></div>
        </div>
        <section class="change-summary" aria-labelledby="change-summary-title">
          <div class="diff-heading">
            <div><p class="section-kicker">Evaluation 影响</p><h4 id="change-summary-title">学习方案变化摘要</h4></div>
            <el-tag type="success" effect="plain">已同步更新</el-tag>
          </div>
          <div class="change-summary-grid">
            <article><span>画像版本</span><strong>{{ changeSummary.profileVersion }}</strong></article>
            <article><span>当前掌握情况</span><strong>{{ changeSummary.mastery }}</strong></article>
            <article><span>路径步骤</span><strong>{{ changeSummary.pathSteps }}</strong></article>
            <article class="change-summary__wide">
              <span>新增或加强的薄弱点</span>
              <div v-if="changeSummary.addedWeakTopics.length" class="topic-tags">
                <el-tag v-for="topic in changeSummary.addedWeakTopics" :key="topic" type="warning" effect="plain">{{ topic }}</el-tag>
              </div>
              <strong v-else>本轮无新增薄弱点</strong>
            </article>
            <article class="change-summary__wide"><span>重新规划原因</span><strong>{{ changeSummary.adjustmentReason || '本次未返回该项变化' }}</strong></article>
            <article class="change-summary__wide"><span>新路径重点</span><strong>{{ changeSummary.newFocus.join(' → ') || '本次未返回该项变化' }}</strong></article>
          </div>
        </section>
        <StatusBanner
          v-if="path?.generation_mode === 'development_rule_based'"
          status="partial"
          message="评价后的路径使用开发降级规划，未标记为结构化模型结果。"
        />
        <el-collapse class="evaluation-raw">
          <el-collapse-item title="查看原始评价反馈">
            <pre class="feedback-text">{{ result.feedback }}</pre>
          </el-collapse-item>
        </el-collapse>
        <DiffComparison title="画像更新前后" :rows="profileRows" empty-text="本轮评价未改变画像字段" />
        <DiffComparison title="路径更新前后" :rows="pathRows" empty-text="本轮评价未调整学习路径" />
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import {computed, reactive, ref, watch} from 'vue';
import {ElMessage} from 'element-plus';
import {ArrowLeft, ArrowRight, Checked} from '@element-plus/icons-vue';
import DiffComparison from './DiffComparison.vue';
import StatusBanner from '@/components/common/StatusBanner.vue';
import {evaluationQuestionFeedback, pathDiff, profileDiff} from '@/utils/content';
import {evaluationChangeSummary} from '@/utils/presentation';
import type {EvaluationResult, LearningPath, QuizDocument, StudentProfile, ViewStatus} from '@/types/api';

const props = defineProps<{
  quiz: QuizDocument | null; result: EvaluationResult | null; status: ViewStatus;
  profile: StudentProfile | null; previousProfile: StudentProfile | null;
  path: LearningPath | null; previousPath: LearningPath | null;
}>();
const emit = defineEmits<{(event: 'submit', answers: Record<string, string>, minutes: number): void}>();
const answers = reactive<Record<string, string>>({});
const timeSpent = ref(12);
const currentIndex = ref(0);
const currentQuestion = computed(() => props.quiz?.questions[currentIndex.value] ?? null);
const questionIds = computed(() => props.quiz?.questions.map((question) => question.id) ?? []);
const answeredCount = computed(() => questionIds.value.filter((id) => answers[id]?.trim()).length);
const unansweredCount = computed(() => questionIds.value.length - answeredCount.value);
const completionPercentage = computed(() => questionIds.value.length ? Math.round(answeredCount.value / questionIds.value.length * 100) : 0);
const incorrectCount = computed(() => props.result && props.quiz
  ? props.quiz.questions.filter((question) => ['incorrect', 'partial'].includes(questionResult(question.id).status)).length
  : 0);
const quizFingerprint = computed(() => JSON.stringify(
  props.quiz?.questions.map((question) => ({id: question.id, question: question.question, options: question.options})) ?? [],
));
const profileRows = computed(() => profileDiff(props.previousProfile, props.profile));
const pathRows = computed(() => pathDiff(props.previousPath, props.path));
const changeSummary = computed(() => evaluationChangeSummary(
  props.previousProfile, props.profile, props.previousPath, props.path, props.result,
));
const suggestion = computed(() => props.result?.passed ? '进入学习路径的下一步骤，并用应用实践巩固当前主题。' : `优先复习${props.result?.weak_topics.join('、') || '当前主题'}，完成讲解与实践资源后再次练习。`);

watch(quizFingerprint, () => {
  Object.keys(answers).forEach((key) => delete answers[key]);
  timeSpent.value = 12;
  currentIndex.value = 0;
});
function retryEvaluation() { emit('submit', {...answers}, timeSpent.value); }
function submitEvaluation() {
  if (props.result || props.status === 'loading') return;
  if (unansweredCount.value) {
    const firstUnanswered = questionIds.value.findIndex((id) => !answers[id]?.trim());
    if (firstUnanswered >= 0) currentIndex.value = firstUnanswered;
    ElMessage.warning(`还有 ${unansweredCount.value} 题未作答，已定位到第一道未答题。`);
    return;
  }
  emit('submit', {...answers}, timeSpent.value);
}
function levelLabel(level: string) { return ({basic: '基础', intermediate: '进阶', advanced: '挑战'} as Record<string, string>)[level] ?? level; }
function typeLabel(type: string) { return ({single_choice: '单选题', short_answer: '简答题', comprehensive: '综合题'} as Record<string, string>)[type] ?? type; }
function questionResult(questionId: string) { return evaluationQuestionFeedback(props.result?.feedback ?? '', questionId); }
</script>
