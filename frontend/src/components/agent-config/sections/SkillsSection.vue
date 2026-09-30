<template>
  <section class="agent-editor-card">
    <div class="agent-section-heading">
      <div>
        <h2>Skill Registry</h2>
        <p>列出可绑定的平台与私有 Skill。新建声明式 Skill 会写入当前 draft；未确认的外部导入不会出现在勾选列表。</p>
      </div>
      <button class="agent-btn agent-btn-soft agent-skill-create-btn" type="button" @click="startCreate">新建 Skill</button>
    </div>
    <p v-if="formError" class="agent-error">{{ formError }}</p>
    <form v-if="editor" class="agent-skill-form" data-skill-form="true" @submit.prevent="saveEditor">
      <label class="agent-field">
        <span>名称</span>
        <input v-model="editor.name" data-skill-field="name" maxlength="80" placeholder="例如：每日简报" />
      </label>
      <label class="agent-field">
        <span>说明</span>
        <input v-model="editor.description" data-skill-field="description" maxlength="200" placeholder="何时使用这个 Skill" />
      </label>
      <label class="agent-field">
        <span>指令</span>
        <textarea v-model="editor.instructions" data-skill-field="instructions" rows="6" maxlength="8000" placeholder="当用户要简报时 ..." />
      </label>
      <div class="agent-skill-form-grid">
        <label class="agent-field">
          <span>风险</span>
          <select v-model="editor.risk_level" data-skill-field="risk_level">
            <option v-for="item in riskOptions" :key="item.value" :value="item.value">{{ item.label }}</option>
          </select>
        </label>
        <label class="agent-field">
          <span>审批</span>
          <select v-model="editor.approval_mode" data-skill-field="approval_mode">
            <option v-for="item in approvalOptions" :key="item.value" :value="item.value">{{ item.label }}</option>
          </select>
        </label>
      </div>
      <div class="agent-skill-form-actions">
        <button class="agent-btn agent-btn-soft agent-skill-save-btn" type="button" :disabled="saving || !canSave" @click="saveEditor">{{ saving ? "保存中..." : (editor.skill_id ? "保存编辑" : "创建并绑定草稿") }}</button>
        <button class="agent-btn agent-btn-ghost" type="button" :disabled="saving" @click="cancelEditor">取消</button>
      </div>
    </form>
    <div class="agent-skill-list">
      <label v-for="skill in bindableSkills" :key="skill.skill_id" class="agent-skill-row" :class="{ 'is-editing': editor?.skill_id === skill.skill_id }" :data-skill-id="skill.skill_id">
        <input v-model="selectedSkillIds" type="checkbox" :value="skill.skill_id" @change="persistBindings" />
        <span class="agent-skill-copy">
          <strong>{{ skill.name }}</strong>
          <small>{{ skill.description || skill.code }} · {{ scopeLabel(skill) }}</small>
        </span>
        <span class="agent-risk" :class="`is-${skill.risk_level}`">{{ RISK_LABELS[skill.risk_level] || skill.risk_level }}</span>
        <button v-if="isUserSkill(skill)" class="agent-btn agent-btn-ghost agent-skill-edit-btn" type="button" @click.prevent="startEdit(skill)">编辑</button>
      </label>
      <p v-if="!bindableSkills.length" class="agent-side-empty">当前实例暂无可用 Skill。</p>
    </div>
    <div class="agent-external-skill">
      <h3>外部 Skill</h3>
      <div class="agent-inline-form">
        <input v-model="skillQuery" placeholder="搜索外部 Skill（默认 Mock Provider）" @keyup.enter="emit('search')" />
        <button class="agent-btn agent-btn-soft" type="button" :disabled="skillSearching" @click="emit('search')">搜索</button>
      </div>
      <div v-for="candidate in candidates" :key="String(candidate.candidate_id)" class="agent-candidate">
        <div>
          <strong>{{ candidate.name }}</strong>
          <small>{{ candidate.source_uri }} @ {{ candidate.source_ref }}</small>
        </div>
        <button class="agent-btn agent-btn-ghost" type="button" :disabled="importing" @click="emit('importCandidate', candidate)">{{ importing ? "扫描中..." : "下载并扫描" }}</button>
      </div>
      <div v-for="item in imports" :key="item.import_id" class="agent-import-result" :data-import-status="item.status">
        <strong>{{ item.source_metadata.name || item.source_uri }}</strong>
        <span>{{ importStatusLabel(item.status) }}</span>
        <small v-if="item.content_digest">digest: {{ item.content_digest }}</small>
        <small v-if="item.scan_report">扫描：{{ scanSummary(item.scan_report) }}</small>
        <small v-if="item.scan_report">{{ scanDetails(item.scan_report) }} · ref {{ item.source_ref }}</small>
        <button v-if="item.status === 'awaiting_confirmation'" class="agent-btn agent-btn-soft" type="button" @click="emit('confirmImport', item)">确认导入</button>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute } from "vue-router";
import {
  createAgentSkill,
  patchAgentSkill,
  updateAgentSkills,
  type SkillImport,
  type SkillRecord,
} from "../../../api/agentConfig";
import { RISK_LABELS, importStatusLabel, scanDetails, scanSummary } from "../../../lib/agentConfig";
import { apiErrorMessage } from "../../../lib/errors";

const props = defineProps<{
  skills: SkillRecord[];
  candidates: Array<Record<string, unknown>>;
  imports: SkillImport[];
  skillSearching: boolean;
  importing: boolean;
}>();

const selectedSkillIds = defineModel<string[]>("selectedSkillIds", { required: true });
const skillQuery = defineModel<string>("skillQuery", { required: true });

const emit = defineEmits<{
  search: [];
  importCandidate: [candidate: Record<string, unknown>];
  confirmImport: [item: SkillImport];
}>();

type SkillEditor = {
  skill_id: string;
  name: string;
  description: string;
  instructions: string;
  risk_level: string;
  approval_mode: string;
};

const route = useRoute();
const agentInstanceId = computed(() => String(route.params.agentInstanceId || ""));
const localSkills = ref<SkillRecord[]>([]);
const editor = ref<SkillEditor | null>(null);
const formError = ref("");
const saving = ref(false);

const riskOptions = [
  { value: "low", label: RISK_LABELS.low },
  { value: "medium", label: RISK_LABELS.medium },
  { value: "high", label: RISK_LABELS.high },
];

const approvalOptions = [
  { value: "auto", label: "自动通过" },
  { value: "once", label: "每次询问" },
  { value: "session", label: "会话内记住" },
  { value: "always", label: "始终审批" },
];

const canSave = computed(() => Boolean(editor.value?.name.trim()));

const bindableSkills = computed(() => localSkills.value.filter((item) => isBindable(item)));

watch(
  () => props.skills,
  (items) => {
    const next = new Map(localSkills.value.map((item) => [item.skill_id, item]));
    for (const item of items || []) {
      next.set(item.skill_id, { ...next.get(item.skill_id), ...item });
    }
    localSkills.value = Array.from(next.values());
  },
  { immediate: true, deep: true },
);

function isUserSkill(skill: SkillRecord) {
  return skill.owner_scope === "user" && (skill.source_type === "custom" || !skill.source_type);
}

function isBindable(skill: SkillRecord) {
  const status = String(skill.status || "active");
  if (status !== "active") return false;
  return skill.owner_scope === "platform" || skill.owner_scope === "user";
}

function scopeLabel(skill: SkillRecord) {
  if (skill.owner_scope === "platform") return "平台预设";
  return skill.source_type === "custom" ? "用户新建" : "用户私有";
}

function emptyEditor(): SkillEditor {
  return {
    skill_id: "",
    name: "",
    description: "",
    instructions: "",
    risk_level: "medium",
    approval_mode: "once",
  };
}

function startCreate() {
  formError.value = "";
  editor.value = emptyEditor();
}

function startEdit(skill: SkillRecord) {
  if (!isUserSkill(skill)) return;
  formError.value = "";
  editor.value = {
    skill_id: skill.skill_id,
    name: skill.name,
    description: skill.description || "",
    instructions: skill.instructions || "",
    risk_level: skill.risk_level || "medium",
    approval_mode: skill.approval_mode || "once",
  };
}

function cancelEditor() {
  editor.value = null;
  formError.value = "";
}

function upsertSkill(skill: SkillRecord) {
  const idx = localSkills.value.findIndex((item) => item.skill_id === skill.skill_id);
  if (idx >= 0) localSkills.value.splice(idx, 1, { ...localSkills.value[idx], ...skill });
  else localSkills.value.push(skill);
}

function bindCreated(skillId: string) {
  if (!selectedSkillIds.value.includes(skillId)) {
    selectedSkillIds.value = [...selectedSkillIds.value, skillId];
  }
}

async function persistBindings() {
  const id = agentInstanceId.value;
  if (!id) return;
  formError.value = "";
  try {
    await updateAgentSkills(id, selectedSkillIds.value);
  } catch (err) {
    formError.value = apiErrorMessage(err, "保存 Skill 勾选失败");
  }
}

async function saveEditor() {
  const current = editor.value;
  const id = agentInstanceId.value;
  if (!current || !id || !current.name.trim()) return;
  saving.value = true;
  formError.value = "";
  const payload = {
    name: current.name.trim(),
    description: current.description.trim(),
    instructions: current.instructions,
    risk_level: current.risk_level,
    approval_mode: current.approval_mode,
  };
  try {
    if (current.skill_id) {
      await patchAgentSkill(id, current.skill_id, {
        ...payload,
        enabled: selectedSkillIds.value.includes(current.skill_id),
      });
      const existing = localSkills.value.find((item) => item.skill_id === current.skill_id);
      upsertSkill({
        ...(existing as SkillRecord),
        skill_id: current.skill_id,
        name: payload.name,
        description: payload.description,
        instructions: payload.instructions,
        risk_level: payload.risk_level,
        approval_mode: payload.approval_mode,
        owner_scope: existing?.owner_scope || "user",
        source_type: existing?.source_type || "custom",
        code: existing?.code || payload.name,
        status: existing?.status || "active",
      });
    } else {
      const created = await createAgentSkill(id, payload);
      upsertSkill(created);
      bindCreated(created.skill_id);
    }
    editor.value = null;
  } catch (err) {
    formError.value = apiErrorMessage(err, current.skill_id ? "保存 Skill 失败" : "新建 Skill 失败");
  } finally {
    saving.value = false;
  }
}
</script>
