<script setup lang="ts">
import { computed, ref, watch } from "vue";

export type HitlKind = "media" | "import" | "skill" | "script" | "tool";

const props = defineProps<{
  visible: boolean;
  tool?: unknown;
  prompt: string;
  params: Record<string, unknown>;
  disabled?: boolean;
  kind?: HitlKind;
  reason?: string;
  resourceCode?: string;
  detail?: string;
}>();
const emit = defineEmits<{
  approve: [payload: { prompt: string; params: Record<string, unknown> }];
  skip: [];
  reject: [];
}>();

const prompt = ref(props.prompt);
const paramsText = ref(JSON.stringify(props.params || {}, null, 2));
const isMedia = computed(() => !props.kind || props.kind === "media");
const hitlKind = computed(() => (isMedia.value ? "media" : props.kind) as HitlKind);

watch(
  () => [props.prompt, props.params],
  () => {
    prompt.value = props.prompt;
    paramsText.value = JSON.stringify(props.params || {}, null, 2);
  },
);

const heading = computed(() => {
  switch (props.kind) {
    case "import":
      return "Skill 导入审批";
    case "skill":
      return "Skill 使用审批";
    case "script":
      return "Skill 脚本审批";
    case "tool":
      return props.tool === "send_email" ? "工具审批：发送邮件" : "工具执行审批";
    default:
      return "";
  }
});

const description = computed(() => {
  if (isMedia.value) return "生成前需要人工审核。审核完成前不能继续发消息。";
  if (props.reason) return String(props.reason);
  switch (props.kind) {
    case "import":
      return "外部 Skill 导入需要独立导入审批，批准前不会写入 Registry。";
    case "skill":
      return "该 Skill 需要独立使用审批。Skill 批准不会放行脚本或工具。";
    case "script":
      return "该 Skill 脚本需要独立脚本审批，不会继承 Skill 或工具权限。";
    case "tool":
      return props.tool === "send_email"
        ? "发送邮件必须先完成独立工具审批，不能直接发送。"
        : "该工具需要独立执行审批，不会被 Skill 或脚本批准绕过。";
    default:
      return "生成前需要人工审核。审核完成前不能继续发消息。";
  }
});

function approve() {
  let params = props.params || {};
  try {
    params = JSON.parse(paramsText.value || "{}");
  } catch {
    params = props.params || {};
  }
  emit("approve", { prompt: prompt.value, params });
}

function secondary() {
  if (isMedia.value) emit("skip");
  else emit("reject");
}
</script>

<template>
  <section v-if="visible" class="agent-hitl" :data-hitl-kind="hitlKind">
    <p v-if="heading"><strong>{{ heading }}</strong></p>
    <p>{{ description }}</p>
    <p v-if="tool">工具：{{ tool }}</p>
    <p v-if="resourceCode">资源：{{ resourceCode }}</p>
    <p v-if="detail">{{ detail }}</p>
    <template v-if="isMedia">
      <label class="agent-field">
        Prompt
        <textarea v-model="prompt" rows="3" />
      </label>
      <label class="agent-field">
        Params JSON
        <textarea v-model="paramsText" rows="4" />
      </label>
    </template>
    <div class="agent-hitl-actions">
      <button class="agent-btn" type="button" :disabled="disabled" @click="approve">{{ isMedia ? "Approve" : "批准" }}</button>
      <button class="agent-btn agent-btn-ghost" type="button" :disabled="disabled" @click="secondary">{{ isMedia ? "Skip" : "拒绝" }}</button>
    </div>
  </section>
</template>
