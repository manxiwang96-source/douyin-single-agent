<template>
  <div class="agent-editor-page">
    <AgentConfigTopbar :status="config?.status" :saved-at="savedAt" :saving="saving" @back="router.push({ name: 'plaza' })" @save="saveDraft" @publish="publish" />

    <p v-if="error" class="agent-error agent-editor-error">{{ error }}</p>
    <div v-if="loading" class="agent-editor-loading">正在加载配置...</div>
    <main v-else class="agent-editor-layout">
      <AgentConfigNav :agent-title="agentTitle" :active-section="activeSection" :sections="EDITOR_SECTIONS" @select="activeSection = $event" />

      <section class="agent-editor-main agent-editor-section-slot">
        <ModelSection v-show="activeSection === 'model'" :agent-title="agentTitle" :config="config" />
        <PromptSection v-show="activeSection === 'prompt'" :draft="draft" :templates="templates" :optimizing="optimizing" :optimization="optimization" @optimize="optimizePrompt" @apply-template="applyTemplate" @accept-optimization="acceptOptimization" @discard-optimization="optimization = null" />
        <WelcomeSection v-show="activeSection === 'welcome'" :draft="draft" />
        <ExamplesSection v-show="activeSection === 'examples'" :draft="draft" @add="addExample" @remove="removeExample" />
        <KnowledgeSection v-show="activeSection === 'knowledge'" :draft="draft" :documents="knowledgeDocuments" />
        <WorkflowSection v-show="activeSection === 'workflow'" />
        <ToolsSection v-show="activeSection === 'tools'" :draft="draft" />
        <SkillsSection v-show="activeSection === 'skills'" :skills="skills" v-model:selected-skill-ids="selectedSkillIdsModel" v-model:skill-query="skillQuery" :candidates="candidates" :imports="imports" :skill-searching="skillSearching" :importing="importing" @search="searchExternalSkills" @import-candidate="importExternalSkill" @confirm-import="confirmImport" />
        <ExperienceSection v-show="activeSection === 'experience'" />
        <MemorySection v-show="activeSection === 'memory'" />
        <VersionsSection v-show="activeSection === 'versions'" />
        <ApprovalsSection v-show="activeSection === 'approvals'" :approvals="approvals" @refresh="loadApprovals" @decide="decide" />
      </section>

      <AgentConfigDebugPane :agent-title="agentTitle" :draft="draft" :preview-input="previewInput" :preview-answer="previewAnswer" @update:preview-input="previewInput = $event" @preview="runPreview" />
    </main>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import AgentConfigDebugPane from "../components/agent-config/AgentConfigDebugPane.vue";
import AgentConfigNav from "../components/agent-config/AgentConfigNav.vue";
import AgentConfigTopbar from "../components/agent-config/AgentConfigTopbar.vue";
import ApprovalsSection from "../components/agent-config/sections/ApprovalsSection.vue";
import ExamplesSection from "../components/agent-config/sections/ExamplesSection.vue";
import ExperienceSection from "../components/agent-config/sections/ExperienceSection.vue";
import KnowledgeSection from "../components/agent-config/sections/KnowledgeSection.vue";
import MemorySection from "../components/agent-config/sections/MemorySection.vue";
import ModelSection from "../components/agent-config/sections/ModelSection.vue";
import PromptSection from "../components/agent-config/sections/PromptSection.vue";
import SkillsSection from "../components/agent-config/sections/SkillsSection.vue";
import ToolsSection from "../components/agent-config/sections/ToolsSection.vue";
import VersionsSection from "../components/agent-config/sections/VersionsSection.vue";
import WelcomeSection from "../components/agent-config/sections/WelcomeSection.vue";
import WorkflowSection from "../components/agent-config/sections/WorkflowSection.vue";
import { apiErrorMessage } from "../lib/errors";
import { EDITOR_SECTIONS, normalizeExamples, type AgentConfigDraft, type EditorSectionId } from "../lib/agentConfig";
import { getAgentSidebar } from "../api/agents";
import { confirmSkillImport, decideApproval, getAgentConfig, listAgentKnowledge, listPromptTemplates, listSkillCatalog, listAgentSkills, listApprovals, optimizeAgentPrompt, previewAgentDraft, publishAgentConfig, searchSkills, startSkillImport, updateAgentConfig, updateAgentSkills, type AgentConfig, type ApprovalRecord, type KnowledgeDocument, type PromptTemplate, type SkillImport, type SkillRecord } from "../api/agentConfig";

const route = useRoute();
const router = useRouter();
const agentInstanceId = String(route.params.agentInstanceId || "");
const loading = ref(true);
const saving = ref(false);
const error = ref("");
const savedAt = ref("");
const activeSection = ref<EditorSectionId>("prompt");
const agentTitle = ref("智能体");
const config = ref<AgentConfig | null>(null);
const templates = ref<PromptTemplate[]>([]);
const skills = ref<SkillRecord[]>([]);
const knowledgeDocuments = ref<KnowledgeDocument[]>([]);
const selectedSkillIdsModel = ref<string[]>([]);
const approvals = ref<ApprovalRecord[]>([]);
const skillQuery = ref("");
const candidates = ref<Array<Record<string, unknown>>>([]);
const imports = ref<SkillImport[]>([]);
const skillSearching = ref(false);
const importing = ref(false);
const optimizing = ref(false);
const optimization = ref<{ optimized_prompt: string; change_summary: string; risk_notice: string } | null>(null);
const previewInput = ref("");
const previewAnswer = ref("");
const draft = reactive<AgentConfigDraft>({ system_prompt: "", welcome_message: "", example_questions: [], enabled_tool_codes: ["get_current_datetime"], workflow_codes: [], knowledge_document_ids: [] });

function copyConfig(value: AgentConfig) {
  config.value = value;
  draft.system_prompt = value.system_prompt || "";
  draft.welcome_message = value.welcome_message || "";
  draft.example_questions = [...(value.example_questions || [])];
  draft.enabled_tool_codes = [...(value.enabled_tool_codes || ["get_current_datetime"])];
  draft.workflow_codes = [...(value.workflow_codes || [])];
  draft.knowledge_document_ids = [...(value.knowledge_document_ids || [])];
}

async function loadApprovals() {
  if (!config.value) return;
  approvals.value = (await listApprovals(agentInstanceId, config.value.config_version_id)).items;
}

async function load() {
  loading.value = true;
  error.value = "";
  try {
    const [nextConfig, templateResult, catalogResult, selectedResult, knowledgeResult, sidebar] = await Promise.all([
      getAgentConfig(agentInstanceId),
      listPromptTemplates(),
      listSkillCatalog(),
      listAgentSkills(agentInstanceId),
      listAgentKnowledge(agentInstanceId),
      getAgentSidebar(agentInstanceId),
    ]);
    copyConfig(nextConfig);
    templates.value = templateResult.items;
    skills.value = catalogResult.items;
    selectedSkillIdsModel.value = selectedResult.items.map((item) => item.skill_id);
    knowledgeDocuments.value = knowledgeResult.items;
    if (!draft.knowledge_document_ids.length) draft.knowledge_document_ids = [...knowledgeResult.selected_document_ids];
    agentTitle.value = String(sidebar.title || sidebar.agent_title || "智能体");
    await loadApprovals();
  } catch (err) {
    error.value = apiErrorMessage(err, "加载智能体配置失败");
  } finally {
    loading.value = false;
  }
}

async function saveDraft(): Promise<boolean> {
  saving.value = true;
  error.value = "";
  try {
    const next = await updateAgentConfig(agentInstanceId, {
      system_prompt: draft.system_prompt,
      welcome_message: draft.welcome_message,
      example_questions: normalizeExamples(draft.example_questions),
      enabled_tool_codes: Array.from(new Set(["get_current_datetime", ...draft.enabled_tool_codes])),
      workflow_codes: draft.workflow_codes,
      knowledge_document_ids: draft.knowledge_document_ids,
    });
    await updateAgentSkills(agentInstanceId, selectedSkillIdsModel.value);
    copyConfig(next);
    savedAt.value = new Date().toLocaleTimeString("zh-CN");
    return true;
  } catch (err) {
    error.value = apiErrorMessage(err, "保存草稿失败");
    return false;
  } finally {
    saving.value = false;
  }
}

async function publish() {
  if (!await saveDraft()) return;
  try {
    config.value = await publishAgentConfig(agentInstanceId);
    savedAt.value = new Date().toLocaleTimeString("zh-CN");
  } catch (err) {
    error.value = apiErrorMessage(err, "发布配置失败");
  }
}

function applyTemplate(template: PromptTemplate) {
  draft.system_prompt = template.prompt;
  activeSection.value = "prompt";
}

function addExample() {
  if (draft.example_questions.length < 10) draft.example_questions.push("");
}

function removeExample(index: number) {
  draft.example_questions.splice(index, 1);
}

async function optimizePrompt() {
  optimizing.value = true;
  try {
    optimization.value = await optimizeAgentPrompt(agentInstanceId, draft.system_prompt);
  } catch (err) {
    error.value = apiErrorMessage(err, "提示词优化失败");
  } finally {
    optimizing.value = false;
  }
}

async function decide(approval: ApprovalRecord, approved: boolean) {
  try {
    await decideApproval(approval.approval_id, approved, approved ? "用户在配置页批准" : "用户在配置页拒绝");
    await loadApprovals();
  } catch (err) {
    error.value = apiErrorMessage(err, "审批决策失败");
  }
}

function acceptOptimization() {
  if (optimization.value) draft.system_prompt = optimization.value.optimized_prompt;
  optimization.value = null;
}

async function searchExternalSkills() {
  skillSearching.value = true;
  try {
    candidates.value = (await searchSkills(skillQuery.value)).items;
  } catch (err) {
    error.value = apiErrorMessage(err, "Skill 搜索失败");
  } finally {
    skillSearching.value = false;
  }
}

async function importExternalSkill(candidate: Record<string, unknown>) {
  importing.value = true;
  try {
    const item = await startSkillImport(agentInstanceId, String(candidate.candidate_id));
    imports.value.unshift(item);
  } catch (err) {
    error.value = apiErrorMessage(err, "Skill 下载或扫描失败");
  } finally {
    importing.value = false;
  }
}

async function confirmImport(item: SkillImport) {
  try {
    const skill = await confirmSkillImport(item.import_id);
    skills.value.push(skill);
    selectedSkillIdsModel.value.push(skill.skill_id);
    item.status = "confirmed";
  } catch (err) {
    error.value = apiErrorMessage(err, "确认导入失败");
  }
}

async function runPreview() {
  const input = previewInput.value.trim();
  if (!input) return;
  try {
    const result = await previewAgentDraft(agentInstanceId, input);
    previewAnswer.value = result.answer;
  } catch (err) {
    error.value = apiErrorMessage(err, "草稿预览失败");
  } finally {
    previewInput.value = "";
  }
}

onMounted(load);
</script>
