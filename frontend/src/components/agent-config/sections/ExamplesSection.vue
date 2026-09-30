<template>
  <section class="agent-editor-card agent-examples-section">
    <div class="agent-section-heading">
      <div>
        <h2>示例问题</h2>
        <p>给用户提供可直接点击的提问示例，最多 {{ maxExamples }} 条，写入 draft.example_questions。</p>
      </div>
      <button class="agent-btn agent-btn-soft agent-example-add" type="button" :disabled="!canAdd" @click="addExample">+ 添加示例</button>
    </div>
    <p class="agent-example-meta">{{ draft.example_questions.length }} / {{ maxExamples }}</p>
    <div v-for="(_, index) in draft.example_questions" :key="index" class="agent-example-row">
      <input v-model="draft.example_questions[index]" maxlength="200" :placeholder="`示例问题 ${index + 1}`" />
      <button class="agent-icon-btn agent-example-remove" type="button" aria-label="删除示例" @click="removeExample(index)">×</button>
    </div>
    <p v-if="!draft.example_questions.length" class="agent-example-empty">还没有示例问题，可添加最多 {{ maxExamples }} 条。</p>
    <button class="agent-btn agent-btn-ghost agent-example-save" type="button" :disabled="saving" @click="saveExamples">{{ saving ? "保存中..." : "写入草稿" }}</button>
    <p v-if="saveError" class="agent-error">{{ saveError }}</p>
    <p v-if="savedAt" class="agent-save-state">已写入草稿 {{ savedAt }}</p>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import { useRoute } from "vue-router";
import { updateAgentConfig } from "../../../api/agentConfig";
import { apiErrorMessage } from "../../../lib/errors";
import { normalizeExamples, type AgentConfigDraft } from "../../../lib/agentConfig";

const maxExamples = 10;

const props = defineProps<{
  draft: AgentConfigDraft;
}>();

const route = useRoute();
const saving = ref(false);
const saveError = ref("");
const savedAt = ref("");
const canAdd = computed(() => props.draft.example_questions.length < maxExamples);

function addExample() {
  if (!canAdd.value) return;
  props.draft.example_questions.push("");
}

function removeExample(index: number) {
  props.draft.example_questions.splice(index, 1);
}

async function saveExamples() {
  const id = String(route.params.agentInstanceId || "");
  if (!id) return;
  saving.value = true;
  saveError.value = "";
  try {
    const questions = normalizeExamples(props.draft.example_questions);
    props.draft.example_questions = [...questions];
    await updateAgentConfig(id, { example_questions: questions });
    savedAt.value = new Date().toLocaleTimeString("zh-CN");
  } catch (err) {
    saveError.value = apiErrorMessage(err, "保存示例问题失败");
  } finally {
    saving.value = false;
  }
}
</script>
