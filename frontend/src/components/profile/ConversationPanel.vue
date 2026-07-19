<template>
  <section class="workspace-panel conversation-panel">
    <div class="panel-title-row">
      <div>
        <p class="section-kicker">自然语言对话</p>
        <h2>说说你的学习情况</h2>
      </div>
      <el-tag class="developer-only" effect="plain">会话 {{ store.studentId }}</el-tag>
    </div>

    <div ref="scrollArea" class="message-list">
      <article v-for="message in store.messages" :key="message.message_id" class="message" :class="`message--${message.role}`">
        <div class="message__role">{{ message.role === 'user' ? '我' : 'EduAgent' }}</div>
        <div class="message__bubble">
          {{ message.content }}<span v-if="message.streaming" class="typing-caret" />
        </div>
      </article>
      <article v-if="store.profileStatus === 'loading'" class="message message--assistant">
        <div class="message__role">EduAgent</div>
        <div class="message__bubble message__bubble--pending"><el-icon class="is-loading"><Loading /></el-icon> 正在理解学习目标、薄弱点与偏好...</div>
      </article>
    </div>

    <StatusBanner
      v-if="store.profileStatus === 'error'"
      status="error"
      message="画像分析未完成，已保留本轮对话，可直接重试。"
      action-label="重试分析"
      @action="store.retryProfile"
    />

    <div class="demo-case-picker" aria-label="演示案例">
      <span class="demo-case-picker__label">演示案例</span>
      <button
        v-for="item in demoCases"
        :key="item.id"
        type="button"
        :title="item.summary"
        :aria-label="`填入演示案例 ${item.code}：${item.name}`"
        @click="applyDemoCase(item)"
      >
        <strong>{{ item.code }}</strong>{{ item.name }}
      </button>
    </div>

    <div class="prompt-suggestions">
      <button v-for="suggestion in suggestions" :key="suggestion" type="button" @click="store.composerDraft = suggestion">{{ suggestion }}</button>
    </div>

    <div class="composer">
      <el-input
        v-model="store.composerDraft"
        type="textarea"
        :rows="3"
        resize="none"
        maxlength="8000"
        placeholder="例如：我是计算机专业学生，机器学习零基础，梯度下降不太懂..."
        aria-label="学习情况输入框"
        @keydown.ctrl.enter="submit"
      />
      <el-button
        type="primary"
        :icon="Promotion"
        :loading="store.profileStatus === 'loading'"
        :disabled="!store.composerDraft.trim()"
        :title="store.composerDraft.trim() ? '发送学习情况（Ctrl+Enter）' : '请先输入学习情况'"
        @click="submit"
      >
        发送
      </el-button>
    </div>
  </section>
</template>

<script setup lang="ts">
import {nextTick, onBeforeUnmount, ref, watch} from 'vue';
import {ElMessage, ElMessageBox} from 'element-plus';
import {Loading, Promotion} from '@element-plus/icons-vue';
import StatusBanner from '@/components/common/StatusBanner.vue';
import {demoCases, type DemoCase} from '@/config/demoCases';
import {useLearningStore} from '@/stores/learning';
import {needsDemoCaseConfirmation} from '@/utils/presentation';

const store = useLearningStore();
const scrollArea = ref<HTMLElement | null>(null);
const suggestions = [
  '我该从哪里开始学机器学习？',
  '我每天只有45分钟，喜欢边写代码边学。',
  '梯度下降一直没弄懂，希望完成课程项目。',
];

async function submit() {
  const content = store.composerDraft;
  store.composerDraft = '';
  await store.sendMessage(content);
}

async function applyDemoCase(item: DemoCase) {
  const hasUserConversation = store.messages.some((message) => message.role === 'user');
  if (needsDemoCaseConfirmation(store.composerDraft, hasUserConversation)) {
    try {
      await ElMessageBox.confirm(
        '演示案例只会替换输入框内容，不会清空或覆盖已有对话。是否继续？',
        '填入演示案例',
        {confirmButtonText: '继续填入', cancelButtonText: '取消', type: 'warning'},
      );
    } catch {
      return;
    }
  }
  store.fillDemoCase(item.input);
  ElMessage.success(`已填入案例 ${item.code}，可修改后再发送`);
}

watch(() => store.messages.length, async () => {
  await nextTick();
  if (scrollArea.value) scrollArea.value.scrollTop = scrollArea.value.scrollHeight;
});

onBeforeUnmount(() => store.stopAssistantAnimation(true));
</script>
