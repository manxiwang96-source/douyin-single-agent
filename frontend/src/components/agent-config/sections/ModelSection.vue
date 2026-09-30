<template>
  <section class="agent-editor-card agent-model-section">
    <div class="agent-section-heading">
      <div>
        <h2>基础信息与模型</h2>
        <p>当前编辑的是 draft，不是已发布配置。</p>
      </div>
      <span class="agent-pill">config v{{ config?.version_no }}</span>
    </div>

    <p class="agent-model-draft-notice">当前编辑的是 draft。本页表单与调试都作用在草稿上，发布前不会改动正式聊天已钉住的版本。</p>

    <div class="agent-model-template-row">
      <span class="agent-pill agent-model-template" :class="{ 'is-ops': isOpsTemplate }">{{ templateLabel }}</span>
      <span class="agent-pill">{{ config?.status === 'published' ? '已发布版本仍在，当前改的是 draft' : 'draft' }}</span>
    </div>

    <label class="agent-field">
      <span>智能体名称</span>
      <input class="agent-model-title" v-model="title" maxlength="30" placeholder="智能体名称" @input="dirty = true" />
    </label>
    <label class="agent-field">
      <span>简介</span>
      <textarea class="agent-model-intro" v-model="intro" maxlength="150" rows="4" placeholder="一句话介绍这个智能体" @input="dirty = true" />
    </label>
    <p v-if="profileError" class="agent-error">{{ profileError }}</p>
    <div class="agent-model-actions">
      <button class="agent-btn agent-btn-ghost agent-model-save" type="button" :disabled="saving" @click="saveProfile">保存基础信息</button>
      <span v-if="savedAt" class="agent-save-state">已保存 {{ savedAt }}</span>
    </div>

    <label class="agent-field">
      <span>对话模型</span>
      <input class="agent-model-name" :value="modelDescription" disabled />
    </label>
    <p class="agent-model-readonly-note">模型由服务端统一配置，本页只读展示说明，不提供模型下拉或切换，也不会新开多模型 API。</p>

    <label class="agent-field">
      <span>当前配置版本</span>
      <input :value="config?.config_version_id" disabled />
    </label>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { getAgentSidebar, listAgentInstances, patchAgentInstance } from "../../../api/agents";
import type { AgentConfig } from "../../../api/agentConfig";
import { apiErrorMessage } from "../../../lib/errors";
import { CUSTOM_TEMPLATE, CUSTOM_TEMPLATE_CODE, DOUYIN_TEMPLATE, DOUYIN_TEMPLATE_CODE } from "../../../lib/plaza";
import { validateIntro, validateTitle } from "../../../lib/title";

const props = defineProps<{
  agentTitle: string;
  config: AgentConfig | null;
}>();

const route = useRoute();
const agentInstanceId = computed(() => String(route.params.agentInstanceId || ""));
const title = ref(props.agentTitle);
const intro = ref("");
const templateCode = ref(CUSTOM_TEMPLATE_CODE);
const dirty = ref(false);
const saving = ref(false);
const profileError = ref("");
const savedAt = ref("");
const modelDescription = "服务端默认对话模型";

const isOpsTemplate = computed(() => templateCode.value === DOUYIN_TEMPLATE_CODE);
const templateLabel = computed(() => (isOpsTemplate.value ? DOUYIN_TEMPLATE.title : CUSTOM_TEMPLATE.title));

watch(
  () => props.agentTitle,
  (value) => {
    if (!dirty.value && value) {
      title.value = value;
    }
  },
);

async function loadProfile() {
  const id = agentInstanceId.value;
  if (!id) return;
  profileError.value = "";
  try {
    const [sidebar, list] = await Promise.all([getAgentSidebar(id), listAgentInstances()]);
    if (!dirty.value) {
      title.value = String(sidebar?.title || sidebar?.agent_title || props.agentTitle || "");
      intro.value = String(sidebar?.intro || "");
    }
    const items = Array.isArray(list?.items) ? list.items : [];
    const item = items.find((entry) => String(entry.agent_instance_id || "") === id);
    templateCode.value = String(item?.template_code || CUSTOM_TEMPLATE_CODE);
  } catch (err) {
    profileError.value = apiErrorMessage(err, "加载基础信息失败");
  }
}

async function saveProfile() {
  const id = agentInstanceId.value;
  if (!id) return;
  profileError.value = "";
  try {
    const nextTitle = validateTitle(title.value);
    const nextIntro = validateIntro(intro.value);
    saving.value = true;
    await patchAgentInstance(id, { title: nextTitle, intro: nextIntro });
    title.value = nextTitle;
    intro.value = nextIntro;
    dirty.value = false;
    savedAt.value = new Date().toLocaleTimeString("zh-CN");
  } catch (err) {
    profileError.value = apiErrorMessage(err, "保存基础信息失败");
  } finally {
    saving.value = false;
  }
}

onMounted(loadProfile);
</script>
