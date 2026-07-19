<template>
  <div class="resource-preview">
    <StatusBanner v-if="renderError" status="error" :message="renderError" />
    <pre v-if="resource.content_format === 'mermaid' && renderError" class="json-preview mermaid-source-fallback"><code>{{ mermaidSource }}</code></pre>
    <div v-if="resource.content_format === 'mermaid'" v-show="!renderError" ref="mermaidHost" class="mermaid-host" />
    <div v-else-if="resource.content_format === 'markdown' || resource.content_format === 'text'" class="prose" v-html="markdownHtml" />
    <div v-else-if="resource.content_format === 'python' && codingIsMarkdown" class="prose" v-html="codingMarkdownHtml" />
    <pre v-else-if="resource.content_format === 'python'" class="hljs code-block"><code v-html="pythonHtml" /></pre>
    <pre v-else class="json-preview">{{ formattedJson }}</pre>
  </div>
</template>

<script setup lang="ts">
import {computed, nextTick, onBeforeUnmount, onMounted, ref, watch} from 'vue';
import hljs from 'highlight.js';
import StatusBanner from '@/components/common/StatusBanner.vue';
import {renderMarkdown} from '@/utils/content';
import {startIsolatedMermaidRender, type MermaidRenderSession} from '@/utils/mermaid';
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

let renderGeneration = 0;
let renderSequence = 0;
let activeRender: MermaidRenderSession | null = null;

function cancelActiveRender() {
  activeRender?.cancel();
  activeRender = null;
}

async function renderMermaid() {
  const generation = ++renderGeneration;
  cancelActiveRender();
  renderError.value = '';
  if (props.resource.content_format !== 'mermaid' || !mermaidHost.value) return;

  const host = mermaidHost.value;
  const resourceId = props.resource.resource_id;
  const resourceContent = props.resource.content;
  const source = mermaidSource.value;
  const isCurrent = () => (
    generation === renderGeneration
    && props.resource.content_format === 'mermaid'
    && props.resource.resource_id === resourceId
    && props.resource.content === resourceContent
  );
  host.replaceChildren();

  try {
    const {default: mermaid} = await import('mermaid');
    if (!isCurrent()) return;

    const temporaryContainer = host.ownerDocument.createElement('div');
    temporaryContainer.className = 'mermaid-render-sandbox';
    temporaryContainer.setAttribute('aria-hidden', 'true');
    host.appendChild(temporaryContainer);

    const safeResourceId = resourceId.replace(/[^a-zA-Z0-9]/g, '') || 'resource';
    const session = startIsolatedMermaidRender({
      mermaid,
      source,
      renderId: `eduagent-${safeResourceId}-${++renderSequence}`,
      container: temporaryContainer,
      isCurrent,
    });
    activeRender = session;
    const outcome = await session.result;
    if (activeRender === session) activeRender = null;
    if (!isCurrent() || outcome.status === 'stale') return;

    host.replaceChildren();
    if (outcome.status === 'success') {
      host.innerHTML = outcome.svg;
      outcome.bindFunctions?.(host);
      return;
    }
    renderError.value = '思维导图暂时无法渲染，已保留原始 Mermaid 源码。';
  } catch {
    if (!isCurrent()) return;
    host.replaceChildren();
    renderError.value = '思维导图暂时无法渲染，已保留原始 Mermaid 源码。';
  }
}

onMounted(renderMermaid);
watch(
  [() => props.resource.resource_id, () => props.resource.content, () => props.resource.content_format],
  async () => { await nextTick(); await renderMermaid(); },
);
onBeforeUnmount(() => {
  renderGeneration += 1;
  cancelActiveRender();
  mermaidHost.value?.replaceChildren();
});
</script>
