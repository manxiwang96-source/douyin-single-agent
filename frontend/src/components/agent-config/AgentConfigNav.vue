<template>
  <aside class="agent-editor-nav">
    <div class="agent-editor-instance"><strong>{{ agentTitle }}</strong><span>草稿配置</span></div>
    <button
      v-for="item in sections"
      :key="item.id"
      class="agent-editor-nav-item"
      :class="{ 'is-active': activeSection === item.id }"
      type="button"
      @click="emit('select', item.id)"
    >
      {{ item.label }}
    </button>
    <div class="agent-editor-boundary">
      <strong>配置边界</strong>
      <p>草稿调试与正式发布分离。线程只使用创建时固定的已发布版本。</p>
      <p class="agent-nav-boundary-extra">当前编辑 draft，右侧调试走草稿；正式聊天只使用创建时钉住的 published。不要把草稿当成已发布配置。</p>
    </div>
  </aside>
</template>

<script setup lang="ts">
defineProps<{
  agentTitle: string;
  activeSection: string;
  sections: ReadonlyArray<{ id: string; label: string }>;
}>();

const emit = defineEmits<{
  select: [id: string];
}>();
</script>