<template>
  <section class="diff-section">
    <div class="diff-heading"><h4>{{ title }}</h4><el-tag effect="plain">{{ rows.length }} 项变化</el-tag></div>
    <el-empty v-if="!rows.length" :description="emptyText" :image-size="56" />
    <div v-else class="diff-table">
      <div class="diff-table__head"><span>字段 / 步骤</span><span>更新前</span><span>更新后</span></div>
      <div v-for="row in rows" :key="row.label" class="diff-table__row"><strong>{{ row.label }}</strong><span>{{ row.before }}</span><span>{{ row.after }}</span></div>
    </div>
  </section>
</template>

<script setup lang="ts">
import type {DiffRow} from '@/utils/content';
defineProps<{title: string; rows: DiffRow[]; emptyText: string}>();
</script>
