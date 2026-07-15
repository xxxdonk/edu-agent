<template>
  <div class="status-banner" :class="`status-banner--${status}`">
    <component :is="icon" class="status-banner__icon" />
    <span>{{ message }}</span>
  </div>
</template>

<script setup lang="ts">
import {computed} from 'vue';
import {CircleCheck, InfoFilled, Loading, WarningFilled} from '@element-plus/icons-vue';
import type {ViewStatus} from '@/types/api';

const props = defineProps<{status: ViewStatus; message: string}>();
const icon = computed(() => ({
  idle: InfoFilled,
  loading: Loading,
  success: CircleCheck,
  empty: InfoFilled,
  partial: WarningFilled,
  error: WarningFilled,
}[props.status]));
</script>
