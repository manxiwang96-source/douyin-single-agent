<template>
  <section class="agent-editor-card agent-experience-section">
    <div class="agent-section-heading">
      <div>
        <h2>开场体验</h2>
        <p>说明正式空聊天是否展示欢迎语和示例。没有独立开关字段，不在本页发明新列。</p>
      </div>
    </div>
    <p class="agent-experience-lead">正式空聊天读取的是已发布配置：有欢迎语就展示欢迎语，有示例问题就可点。草稿改动要发布后才会出现在新的正式聊天。</p>
    <p v-if="loadError" class="agent-error">{{ loadError }}</p>
    <div class="agent-experience-grid">
      <div class="agent-experience-switch" data-experience-welcome>
        <span class="agent-pill" :class="{ 'is-on': showWelcome }">{{ showWelcome ? "将展示" : "不展示" }}</span>
        <div>
          <strong>开场欢迎语</strong>
          <p>{{ showWelcome ? "当前草稿已填写 welcome_message，发布后空聊天会展示。" : "当前草稿欢迎语为空；清空即不展示，没有单独的开关列。" }}</p>
        </div>
      </div>
      <div class="agent-experience-switch" data-experience-examples>
        <span class="agent-pill" :class="{ 'is-on': showExamples }">{{ showExamples ? "将展示" : "不展示" }}</span>
        <div>
          <strong>开场示例问题</strong>
          <p>{{ showExamples ? "当前草稿有 " + exampleCount + " 条示例，发布后可点。" : "当前草稿没有示例问题；空列表即不展示，请到示例分区编辑。" }}</p>
        </div>
      </div>
    </div>
    <p class="agent-experience-note">请到「欢迎语」「示例问题」分区编辑内容。本页只解释开场展示规则。</p>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { getAgentConfig } from "../../../api/agentConfig";
import { apiErrorMessage } from "../../../lib/errors";

const route = useRoute();
const welcomeMessage = ref("");
const exampleCount = ref(0);
const loadError = ref("");

const showWelcome = computed(() => welcomeMessage.value.trim().length > 0);
const showExamples = computed(() => exampleCount.value > 0);

async function loadExperience() {
  const id = String(route.params.agentInstanceId || "");
  if (!id) return;
  loadError.value = "";
  try {
    const config = await getAgentConfig(id);
    welcomeMessage.value = String(config?.welcome_message || "");
    const examples = Array.isArray(config?.example_questions) ? config.example_questions : [];
    exampleCount.value = examples.map((item) => String(item || "").trim()).filter(Boolean).length;
  } catch (err) {
    loadError.value = apiErrorMessage(err, "加载开场体验说明失败");
  }
}

onMounted(loadExperience);
</script>