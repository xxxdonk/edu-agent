<template>
  <section class="workspace-panel issue-panel">
    <div class="panel-title-row">
      <div><p class="section-kicker">系统集成交接</p><h2>后端接口问题记录</h2></div>
      <el-tag :type="issues.length ? 'warning' : 'success'">{{ issues.length }} 条</el-tag>
    </div>
    <el-empty v-if="!issues.length" description="当前未记录到接口问题" :image-size="64" />
    <el-collapse v-else>
      <el-collapse-item v-for="issue in issues" :key="issue.createdAt" :title="`${issue.endpoint} · ${formatDate(issue.createdAt)}`">
        <dl class="issue-details">
          <dt>接口地址</dt><dd><code>{{ issue.endpoint }}</code></dd>
          <dt>请求参数</dt><dd><pre>{{ JSON.stringify(issue.request, null, 2) }}</pre></dd>
          <dt>预期响应</dt><dd>{{ issue.expected }}</dd>
          <dt>实际响应</dt><dd><pre>{{ issue.actual }}</pre></dd>
          <dt>浏览器报错</dt><dd>{{ issue.browserError }}</dd>
          <dt>复现步骤</dt><dd>{{ issue.reproduction.join(' → ') }}</dd>
        </dl>
      </el-collapse-item>
    </el-collapse>
  </section>
</template>

<script setup lang="ts">
import type {ApiIssue} from '@/types/api';
defineProps<{issues: ApiIssue[]}>();
function formatDate(value: string) { return new Intl.DateTimeFormat('zh-CN', {hour: '2-digit', minute: '2-digit', second: '2-digit'}).format(new Date(value)); }
</script>
