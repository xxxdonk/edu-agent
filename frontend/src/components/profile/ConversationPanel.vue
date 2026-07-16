<template>
  <section class="workspace-panel conversation-panel">
    <div class="panel-title-row">
      <div>
        <p class="section-kicker">自然语言对话</p>
        <h2>说说你的学习情况</h2>
      </div>
      <el-tag effect="plain">{{ store.studentId }}</el-tag>
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
        <div class="message__bubble message__bubble--pending"><el-icon class="is-loading"><Loading /></el-icon> 正在提取画像证据...</div>
      </article>
    </div>

    <div class="prompt-suggestions">
      <button v-for="suggestion in suggestions" :key="suggestion" type="button" @click="draft = suggestion">{{ suggestion }}</button>
    </div>

    <div class="composer">
      <el-input
        v-model="draft"
        type="textarea"
        :rows="3"
        resize="none"
        maxlength="8000"
        placeholder="例如：我是计算机专业学生，机器学习零基础，梯度下降不太懂..."
        @keydown.ctrl.enter="submit"
      />
      <el-button type="primary" :icon="Promotion" :loading="store.profileStatus === 'loading'" :disabled="!draft.trim()" @click="submit">
        发送
      </el-button>
    </div>
  </section>
</template>

<script setup lang="ts">
import {nextTick, ref, watch} from 'vue';
import {Loading, Promotion} from '@element-plus/icons-vue';
import {useLearningStore} from '@/stores/learning';

const store = useLearningStore();
const draft = ref('');
const scrollArea = ref<HTMLElement | null>(null);
const suggestions = [
  '我该从哪里开始学机器学习？',
  '我每天只有45分钟，喜欢边写代码边学。',
  '梯度下降一直没弄懂，希望完成课程项目。',
];

async function submit() {
  const content = draft.value;
  draft.value = '';
  await store.sendMessage(content);
}

watch(() => store.messages.length, async () => {
  await nextTick();
  if (scrollArea.value) scrollArea.value.scrollTop = scrollArea.value.scrollHeight;
});
</script>
