<template>
  <header class="agent-editor-topbar agent-topbar-with-boundary">
    <div class="agent-editor-brand">
      <button class="agent-btn agent-btn-ghost agent-topbar-back" type="button" @click="emit('back')">返回广场</button>
      <div>
        <h1>智能体编辑</h1>
        <span class="agent-editor-status">{{ statusLabel }}</span>
      </div>
    </div>
    <div class="agent-editor-actions">
      <span class="agent-save-state">{{ saveStateLabel }}</span>
      <button class="agent-btn agent-btn-ghost" type="button" :disabled="saving" @click="emit('save')">保存草稿</button>
      <button class="agent-btn" type="button" :disabled="saving" @click="emit('publish')">发布配置</button>
    </div>
    <p class="agent-topbar-boundary" data-topbar-boundary>
      当前编辑的是 draft。保存草稿只更新配置页和调试；发布后才会作用于之后新开的正式聊天。已有正式线程仍钉住创建时的 published 版本，再发布不会改旧线程。
    </p>
  </header>
</template>

<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{
  status?: string;
  savedAt: string;
  saving: boolean;
}>();

const emit = defineEmits<{
  back: [];
  save: [];
  publish: [];
}>();

const statusLabel = computed(() => (
  props.status === "published"
    ? "已发布版本"
    : "草稿编辑中"
));

const saveStateLabel = computed(() => {
  if (props.saving) return "保存中...";
  if (props.savedAt) return `已保存 ${props.savedAt}`;
  return "尚未保存草稿";
});
</script>