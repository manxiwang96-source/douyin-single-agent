<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { createAgentInstance } from "../api/agents";
import { fileToDataUrl } from "../lib/avatar";
import { apiErrorMessage } from "../lib/errors";
import { INTRO_MAX, TITLE_MAX, validateIntro, validateTitle } from "../lib/title";
import { DOUYIN_TEMPLATE as TEMPLATE } from "../lib/plaza";

const props = defineProps<{ open: boolean }>();
const emit = defineEmits<{ close: []; created: [] }>();

const step = ref<"template" | "profile">("template");
const title = ref("");
const intro = ref("");
const avatar = ref("");
const preview = ref("");
const error = ref("");
const loading = ref(false);

watch(
  () => props.open,
  (open) => {
    if (open) {
      step.value = "template";
      title.value = "";
      intro.value = "";
      avatar.value = "";
      preview.value = "";
      error.value = "";
      loading.value = false;
    }
  },
);

const titleCount = computed(() => title.value.length);
const introCount = computed(() => intro.value.length);

function chooseTemplate() {
  step.value = "profile";
  error.value = "";
}

async function onAvatar(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) {
    return;
  }
  avatar.value = await fileToDataUrl(file);
  preview.value = avatar.value;
}

async function submit() {
  error.value = "";
  try {
    const nextTitle = validateTitle(title.value);
    const nextIntro = validateIntro(intro.value);
    loading.value = true;
    await createAgentInstance(nextTitle, nextIntro, avatar.value || null);
    emit("created");
    emit("close");
  } catch (err) {
    error.value = apiErrorMessage(err);
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div v-if="open" class="agent-modal-mask" @click.self="emit('close')">
    <div class="agent-modal" role="dialog" aria-modal="true">
      <div class="agent-modal-head">
        <h2>新建智能体</h2>
        <button class="agent-icon-btn" type="button" aria-label="关闭" @click="emit('close')">×</button>
      </div>

      <button
        v-if="step === 'template'"
        class="agent-template is-selected"
        type="button"
        @click="chooseTemplate"
      >
        <strong>{{ TEMPLATE.title }}</strong>
        <p class="agent-subtitle">{{ TEMPLATE.description }}</p>
      </button>

      <form v-else @submit.prevent="submit">
        <div class="agent-profile">
          <div>
            <label class="agent-field">
              名称*
              <input v-model="title" maxlength="30" />
              <span class="agent-counter">{{ titleCount }}/{{ TITLE_MAX }}</span>
            </label>
            <label class="agent-field">
              简介*
              <textarea v-model="intro" maxlength="150" rows="5" />
              <span class="agent-counter">{{ introCount }}/{{ INTRO_MAX }}</span>
            </label>
          </div>
          <label class="agent-avatar-upload">
            <img v-if="preview" :src="preview" alt="" />
            <span v-else>本机上传头像</span>
            <input type="file" accept="image/*" hidden @change="onAvatar" />
          </label>
        </div>
        <p v-if="error" class="agent-error">{{ error }}</p>
        <div class="agent-modal-actions">
          <button class="agent-btn agent-btn-ghost" type="button" @click="emit('close')">取消</button>
          <button class="agent-btn" type="submit" :disabled="loading">{{ loading ? "创建中..." : "新建" }}</button>
        </div>
      </form>
    </div>
  </div>
</template>
