<template>
  <div class="resource-preview">
    <StatusBanner v-if="renderError" status="error" :message="renderError" />
    <div v-if="resource.content_format === 'mermaid'" ref="mermaidHost" class="mermaid-host" />
    <div v-else-if="resource.content_format === 'markdown' || resource.content_format === 'text'" class="prose" v-html="markdownHtml" />
    <div v-else-if="resource.content_format === 'python' && codingIsMarkdown" class="prose" v-html="codingMarkdownHtml" />
    <pre v-else-if="resource.content_format === 'python'" class="hljs code-block"><code v-html="pythonHtml" /></pre>
    <pre v-else class="json-preview">{{ formattedJson }}</pre>
  </div>
</template>

<script setup lang="ts">
import {computed, nextTick, onMounted, ref, watch} from 'vue';
import hljs from 'highlight.js';
import StatusBanner from '@/components/common/StatusBanner.vue';
import {renderMarkdown} from '@/utils/content';
import type {Resource} from '@/types/api';

const props = defineProps<{resource: Resource}>();
const mermaidHost = ref<HTMLElement | null>(null);
const renderError = ref('');
const markdownHtml = computed(() => renderMarkdown(props.resource.content));
const codingIsMarkdown = computed(() => (
  /```(?:python|py)\b/i.test(props.resource.content)
  || /^(?:#{1,6}\s|[-*]\s)/m.test(props.resource.content)
));
const codingMarkdownHtml = computed(() => renderMarkdown(props.resource.content));
const pythonHtml = computed(() => hljs.highlight(props.resource.content, {language: 'python'}).value);
const mermaidSource = computed(() => {
  const content = props.resource.content.trim();
  const fenced = content.match(/^```(?:mermaid)?[ \t]*\r?\n([\s\S]*?)\r?\n```[ \t]*$/i);
  return (fenced?.[1] ?? content).trim();
});
const formattedJson = computed(() => {
  try { return JSON.stringify(JSON.parse(props.resource.content), null, 2); }
  catch { return props.resource.content; }
});

async function renderMermaid() {
  if (props.resource.content_format !== 'mermaid' || !mermaidHost.value) return;
  renderError.value = '';
  try {
    const {default: mermaid} = await import('mermaid');
    mermaid.initialize({startOnLoad: false, securityLevel: 'strict', theme: 'neutral'});
    const resourceId = props.resource.resource_id;
    const result = await mermaid.render(`eduagent-${resourceId.replace(/[^a-zA-Z0-9]/g, '')}-${Date.now()}`, mermaidSource.value);
    if (props.resource.resource_id !== resourceId) return;
    if (mermaidHost.value) mermaidHost.value.innerHTML = result.svg;
  } catch {
    renderError.value = '思维导图渲染失败，已保留原始 Mermaid 内容供检查。';
    if (mermaidHost.value) mermaidHost.value.textContent = props.resource.content;
  }
}

onMounted(renderMermaid);
watch(
  [() => props.resource.resource_id, () => props.resource.content],
  async () => { await nextTick(); await renderMermaid(); },
);
</script>
