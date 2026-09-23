<script setup lang="ts">
import { ref, watch } from "vue";

const props = defineProps<{
  visible: boolean;
  tool?: unknown;
  prompt: string;
  params: Record<string, unknown>;
  disabled?: boolean;
}>();
const emit = defineEmits<{
  approve: [payload: { prompt: string; params: Record<string, unknown> }];
  skip: [];
}>();

const prompt = ref(props.prompt);
const paramsText = ref(JSON.stringify(props.params || {}, null, 2));

watch(
  () => [props.prompt, props.params],
  () => {
    prompt.value = props.prompt;
    paramsText.value = JSON.stringify(props.params || {}, null, 2);
  },
);

function approve() {
  let params = props.params || {};
  try {
    params = JSON.parse(paramsText.value || "{}");
  } catch {
    params = props.params || {};
  }
  emit("approve", { prompt: prompt.value, params });
}
</script>

<template>
  <section v-if="visible" class="agent-hitl">
    <p>生成前需要人工审核。审核完成前不能继续发消息。</p>
    <p v-if="tool">工具：{{ tool }}</p>
    <label class="agent-field">
      Prompt
      <textarea v-model="prompt" rows="3" />
    </label>
    <label class="agent-field">
      Params JSON
      <textarea v-model="paramsText" rows="4" />
    </label>
    <div class="agent-hitl-actions">
      <button class="agent-btn" type="button" :disabled="disabled" @click="approve">Approve</button>
      <button class="agent-btn agent-btn-ghost" type="button" :disabled="disabled" @click="emit('skip')">Skip</button>
    </div>
  </section>
</template>
