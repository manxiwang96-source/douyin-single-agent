<template>
  <section class="agent-editor-card agent-welcome-section">
    <div class="agent-section-heading">
      <div>
        <h2>欢迎语</h2>
        <p>用户首次打开对话时展示，内容写入当前 draft 的 welcome_message。</p>
      </div>
      <button class="agent-btn agent-btn-soft agent-welcome-save" type="button" :disabled="saving" @click="saveWelcome">{{ saving ? "保存中..." : "写入草稿" }}</button>
    </div>
    <textarea
      v-model="draft.welcome_message"
      class="agent-welcome-editor"
      rows="6"
      maxlength="1000"
      placeholder="你好，我可以帮你..."
    />
    <p class="agent-welcome-meta">{{ usedCount }} / 1000 · 先写入草稿，发布后才会出现在正式空聊天。</p>
    <p v-if="saveError" class="agent-error">{{ saveError }}</p>
    <p v-if="savedAt" class="agent-save-state">已写入草稿 {{ savedAt }}</p>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import { useRoute } from "vue-router";
import { updateAgentConfig } from "../../../api/agentConfig";
import { apiErrorMessage } from "../../../lib/errors";
import type { AgentConfigDraft } from "../../../lib/agentConfig";

const props = defineProps<{
  draft: AgentConfigDraft;
}>();

const route = useRoute();
const saving = ref(false);
const saveError = ref("");
const savedAt = ref("");
const usedCount = computed(() => Array.from(props.draft.welcome_message || "").length);

async function saveWelcome() {
  const id = String(route.params.agentInstanceId || "");
  if (!id) return;
  saving.value = true;
  saveError.value = "";
  try {
    await updateAgentConfig(id, { welcome_message: props.draft.welcome_message || "" });
    savedAt.value = new Date().toLocaleTimeString("zh-CN");
  } catch (err) {
    saveError.value = apiErrorMessage(err, "保存欢迎语失败");
  } finally {
    saving.value = false;
  }
}
</script>
