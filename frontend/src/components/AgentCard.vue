<script setup lang="ts">
import { onUnmounted, ref, watch } from "vue";
import { fetchAuthBlob } from "../api/threads";
import { formatDateTime, type AgentCard } from "../lib/plaza";

const props = defineProps<{ card: AgentCard }>();
const emit = defineEmits<{
  click: [id: string];
  edit: [id: string];
  archive: [id: string];
}>();
const avatarSrc = ref("");
let objectUrl = "";

watch(
  () => props.card.avatar_url,
  async (url) => {
    if (objectUrl) {
      URL.revokeObjectURL(objectUrl);
      objectUrl = "";
    }
    avatarSrc.value = "";
    if (!url) {
      return;
    }
    try {
      const blob = await fetchAuthBlob(url);
      objectUrl = URL.createObjectURL(blob);
      avatarSrc.value = objectUrl;
    } catch {
      avatarSrc.value = "";
    }
  },
  { immediate: true },
);

onUnmounted(() => {
  if (objectUrl) {
    URL.revokeObjectURL(objectUrl);
  }
});
</script>

<template>
  <article class="agent-card">
    <button class="agent-card-main" type="button" @click="emit('click', card.agent_instance_id)">
      <div class="agent-card-head">
        <img v-if="avatarSrc" class="agent-avatar" :src="avatarSrc" alt="" />
        <div v-else class="agent-avatar-fallback">{{ card.title.slice(0, 1) || "助" }}</div>
        <h3 class="agent-card-title">{{ card.title }}</h3>
      </div>
      <p class="agent-card-intro">{{ card.intro }}</p>
      <div class="agent-meta">
        <span class="agent-mode">{{ card.agent_mode_label }}</span>
        <span>创建时间 {{ formatDateTime(card.created_at) }}</span>
        <span>最近编辑 {{ formatDateTime(card.updated_at) }}</span>
      </div>
    </button>
    <div class="agent-card-actions">
      <button
        class="agent-btn agent-btn-ghost agent-card-edit"
        type="button"
        @click.stop="emit('edit', card.agent_instance_id)"
      >
        编辑
      </button>
      <button
        class="agent-btn agent-btn-ghost agent-card-archive"
        type="button"
        @click.stop="emit('archive', card.agent_instance_id)"
      >
        归档
      </button>
    </div>
  </article>
</template>
