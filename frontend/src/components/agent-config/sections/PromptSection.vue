<template>
  <section class="agent-editor-card">
    <div class="agent-section-heading">
      <div>
        <h2>提示词</h2>
        <p>普通文本与结构化编辑同一个 draft 字段，保存时拼回 system_prompt。</p>
      </div>
      <button class="agent-btn agent-btn-soft agent-prompt-optimize-btn" type="button" :disabled="optimizing" @click="emit('optimize')">{{ optimizing ? "优化中..." : "一键优化" }}</button>
    </div>
    <div class="agent-prompt-mode" role="tablist" aria-label="提示词编辑模式">
      <button class="agent-prompt-mode-btn" :class="{ 'is-active': mode === 'plain' }" type="button" data-prompt-mode="plain" @click="setMode('plain')">普通文本</button>
      <button class="agent-prompt-mode-btn" :class="{ 'is-active': mode === 'structured' }" type="button" data-prompt-mode="structured" @click="setMode('structured')">结构化</button>
    </div>
    <div class="agent-template-row">
      <button
        v-for="template in templates"
        :key="template.template_id"
        class="agent-template-chip"
        type="button"
        :title="template.description"
        @click="applyTemplate(template)"
      >{{ template.name }}</button>
    </div>
    <p v-if="activeTemplateHint" class="agent-helper">{{ activeTemplateHint }}</p>
    <textarea
      v-if="mode === 'plain'"
      v-model="draft.system_prompt"
      class="agent-prompt-editor"
      rows="15"
      maxlength="10000"
      placeholder="例如：你是品牌客服，只依据已启用知识库回答..."
    />
    <div v-else class="agent-prompt-structured">
      <label class="agent-prompt-field">
        <span>角色</span>
        <textarea data-prompt-field="role" rows="4" maxlength="4000" v-model="structured.role" placeholder="智能体扮演的身份" @input="syncStructured" />
      </label>
      <label class="agent-prompt-field">
        <span>目标</span>
        <textarea data-prompt-field="goal" rows="4" maxlength="4000" v-model="structured.goal" placeholder="需要完成什么" @input="syncStructured" />
      </label>
      <label class="agent-prompt-field">
        <span>边界</span>
        <textarea data-prompt-field="boundary" rows="4" maxlength="4000" v-model="structured.boundary" placeholder="不能做或必须遵守的限制" @input="syncStructured" />
      </label>
      <label class="agent-prompt-field">
        <span>失败处理</span>
        <textarea data-prompt-field="failure" rows="4" maxlength="4000" v-model="structured.failure" placeholder="无法确认或失败时如何说明" @input="syncStructured" />
      </label>
    </div>
    <p class="agent-helper">提示词模板只填充文本，不会自动授予工具或 Skill 权限。</p>
    <div v-if="optimization" class="agent-optimization agent-prompt-compare">
      <strong>优化预览</strong>
      <div class="agent-prompt-compare-grid">
        <section class="agent-prompt-compare-pane">
          <h3>原文</h3>
          <p>{{ optimization.original_prompt || draft.system_prompt }}</p>
        </section>
        <section class="agent-prompt-compare-pane">
          <h3>优化结果</h3>
          <p>{{ optimization.optimized_prompt }}</p>
        </section>
      </div>
      <small>变更说明：{{ optimization.change_summary }}</small>
      <small>风险提示：{{ optimization.risk_notice }}</small>
      <div>
        <button class="agent-btn agent-btn-soft agent-prompt-accept-btn" type="button" @click="acceptOptimization">确认写入草稿</button>
        <button class="agent-btn agent-btn-ghost agent-prompt-discard-btn" type="button" @click="discardOptimization">放弃</button>
      </div>
    </div>
    <div v-if="undoPrompt !== null" class="agent-prompt-undo">
      <button class="agent-btn agent-btn-ghost agent-prompt-undo-btn" type="button" @click="undoOptimization">撤销优化</button>
    </div>
  </section>
</template>

<script setup lang="ts">
import { reactive, ref, watch } from "vue";
import type { PromptOptimizeResult, PromptTemplate } from "../../../api/agentConfig";
import type { AgentConfigDraft } from "../../../lib/agentConfig";

type PromptMode = "plain" | "structured";

type StructuredPrompt = {
  role: string;
  goal: string;
  boundary: string;
  failure: string;
  leftover: string;
};

const FIELD_ALIASES: Record<string, keyof Omit<StructuredPrompt, "leftover">> = {
  角色: "role",
  role: "role",
  目标: "goal",
  goals: "goal",
  边界: "boundary",
  安全边界: "boundary",
  规则: "boundary",
  失败处理: "failure",
  异常处理: "failure",
};

const HEADER_RE = /^(角色|目标|边界|安全边界|规则|失败处理|异常处理|流程|输入|输出|输出格式|风格要求|知识库使用规则|工具与 Skill 使用规则|预期输出|适用工具\/Skill|Role|Goals)[：:]\s*(.*)$/i;

const props = defineProps<{
  draft: AgentConfigDraft;
  templates: PromptTemplate[];
  optimizing: boolean;
  optimization: PromptOptimizeResult | { optimized_prompt: string; change_summary: string; risk_notice: string; original_prompt?: string } | null;
}>();

const emit = defineEmits<{
  optimize: [];
  applyTemplate: [template: PromptTemplate];
  acceptOptimization: [];
  discardOptimization: [];
}>();

const mode = ref<PromptMode>("plain");
const structured = reactive<StructuredPrompt>(emptyStructured());
const undoPrompt = ref<string | null>(null);
const activeTemplateHint = ref("");

function emptyStructured(): StructuredPrompt {
  return { role: "", goal: "", boundary: "", failure: "", leftover: "" };
}

function parseStructured(text: string): StructuredPrompt {
  const result = emptyStructured();
  const trimmed = text.replace(/\r\n/g, "\n").trim();
  if (!trimmed) return result;

  let dest: keyof StructuredPrompt | null = null;
  let sawHeader = false;
  const buckets: Record<keyof StructuredPrompt, string[]> = {
    role: [],
    goal: [],
    boundary: [],
    failure: [],
    leftover: [],
  };

  for (const line of trimmed.split("\n")) {
    const match = line.match(HEADER_RE);
    if (match) {
      sawHeader = true;
      const label = match[1];
      const mapped = FIELD_ALIASES[label] || FIELD_ALIASES[label.toLowerCase()];
      if (mapped) {
        dest = mapped;
        if (match[2]) buckets[mapped].push(match[2]);
      } else {
        dest = "leftover";
        buckets.leftover.push(line);
      }
      continue;
    }
    if (dest) buckets[dest].push(line);
    else buckets.leftover.push(line);
  }

  if (!sawHeader) {
    result.role = trimmed;
    return result;
  }

  result.role = buckets.role.join("\n").trim();
  result.goal = buckets.goal.join("\n").trim();
  result.boundary = buckets.boundary.join("\n").trim();
  result.failure = buckets.failure.join("\n").trim();
  result.leftover = buckets.leftover.join("\n").trim();
  return result;
}

function joinStructured(value: StructuredPrompt): string {
  const parts: string[] = [];
  if (value.role.trim()) parts.push(`角色：${value.role.trim()}`);
  if (value.goal.trim()) parts.push(`目标：${value.goal.trim()}`);
  if (value.boundary.trim()) parts.push(`边界：${value.boundary.trim()}`);
  if (value.failure.trim()) parts.push(`失败处理：${value.failure.trim()}`);
  if (value.leftover.trim()) parts.push(value.leftover.trim());
  return parts.join("\n\n");
}

function setMode(next: PromptMode) {
  if (next === mode.value) return;
  if (next === "structured") {
    Object.assign(structured, parseStructured(props.draft.system_prompt));
  } else {
    props.draft.system_prompt = joinStructured(structured);
  }
  mode.value = next;
}

function syncStructured() {
  props.draft.system_prompt = joinStructured(structured);
}

function applyTemplate(template: PromptTemplate) {
  undoPrompt.value = null;
  activeTemplateHint.value = [template.description, template.variables.length ? `变量：${template.variables.join("、")}` : ""]
    .filter(Boolean)
    .join(" · ");
  emit("applyTemplate", template);
}

function acceptOptimization() {
  undoPrompt.value = props.draft.system_prompt;
  emit("acceptOptimization");
}

function discardOptimization() {
  emit("discardOptimization");
}

function undoOptimization() {
  if (undoPrompt.value === null) return;
  props.draft.system_prompt = undoPrompt.value;
  if (mode.value === "structured") Object.assign(structured, parseStructured(undoPrompt.value));
  undoPrompt.value = null;
}

watch(
  () => props.draft.system_prompt,
  (value) => {
    if (mode.value !== "structured") return;
    if (joinStructured(structured) === value) return;
    Object.assign(structured, parseStructured(value));
  },
);
</script>
