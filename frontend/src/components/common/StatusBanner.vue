<template>
  <div class="status-banner" :class="`status-banner--${status}`" :role="status === 'error' ? 'alert' : 'status'">
    <component :is="icon" class="status-banner__icon" :class="{'is-loading': status === 'loading'}" aria-hidden="true" />
    <span class="status-banner__message">{{ message }}</span>
    <el-button v-if="actionLabel" class="status-banner__action" size="small" plain @click="$emit('action')">
      {{ actionLabel }}
    </el-button>
  </div>
</template>

<script setup lang="ts">
import {computed} from 'vue';
import {CircleCheck, InfoFilled, Loading, WarningFilled} from '@element-plus/icons-vue';
import type {ViewStatus} from '@/types/api';

const props = defineProps<{status: ViewStatus; message: string; actionLabel?: string}>();
defineEmits<{(event: 'action'): void}>();
const icon = computed(() => ({
  idle: InfoFilled,
  loading: Loading,
  success: CircleCheck,
  empty: InfoFilled,
  partial: WarningFilled,
  error: WarningFilled,
}[props.status]));
</script>
