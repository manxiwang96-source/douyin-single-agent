import { reactive } from "vue";
import { http } from "./http";

export type AgentConfig = {
  config_version_id: string;
  user_id: string;
  agent_instance_id: string;
  version_no: number;
  status: "draft" | "published" | string;
  system_prompt: string;
  welcome_message: string;
  example_questions: string[];
  enabled_tool_codes: string[];
  workflow_codes: string[];
  knowledge_document_ids: string[];
  created_at?: string;
  updated_at?: string;
};

export type SkillRecord = {
  skill_id: string;
  owner_scope: "platform" | "user" | string;
  owner_user_id?: string | null;
  source_type: string;
  code: string;
  name: string;
  description: string;
  trigger_description?: string;
  instructions?: string;
  source_uri?: string | null;
  source_ref?: string | null;
  content_digest?: string | null;
  risk_level: "low" | "medium" | "high" | string;
  approval_mode: "auto" | "once" | "always" | string;
  status: string;
};

export type PromptTemplate = {
  template_id: string;
  name: string;
  description: string;
  prompt: string;
  variables: string[];
  tool_codes: string[];
  skill_codes: string[];
};

export type SkillImport = {
  import_id: string;
  source_uri: string;
  source_ref: string;
  status: string;
  source_metadata: Record<string, unknown>;
  scan_report: Record<string, unknown>;
  content_digest?: string | null;
  imported_skill_id?: string | null;
  failure_reason?: string;
};

export type ApprovalRecord = {
  approval_id: string;
  user_id: string;
  agent_instance_id: string;
  config_version_id: string;
  thread_id: string;
  approval_kind: "import" | "skill" | "script" | "tool" | string;
  resource_code: string;
  status: "pending" | "approved" | "rejected" | string;
  reason?: string;
  requested_at?: string;
  decided_at?: string | null;
};

export async function getAgentConfig(agentInstanceId: string): Promise<AgentConfig> {
  const response = await http.get(`/v1/agent-instances/${agentInstanceId}/config`);
  return response.data;
}

export async function updateAgentConfig(
  agentInstanceId: string,
  fields: Partial<Pick<AgentConfig, "system_prompt" | "welcome_message" | "example_questions" | "enabled_tool_codes" | "workflow_codes" | "knowledge_document_ids">>,
): Promise<AgentConfig> {
  const response = await http.put(`/v1/agent-instances/${agentInstanceId}/config/draft`, fields);
  return response.data;
}

export async function publishAgentConfig(agentInstanceId: string): Promise<AgentConfig> {
  const response = await http.post(`/v1/agent-instances/${agentInstanceId}/config/publish`);
  return response.data;
}
export type PromptOptimizeResult = {
  original_prompt: string;
  optimized_prompt: string;
  change_summary: string;
  risk_notice: string;
};

export async function optimizeAgentPrompt(agentInstanceId: string, prompt: string): Promise<PromptOptimizeResult> {
  const response = await http.post(`/v1/agent-instances/${agentInstanceId}/config/draft/prompt/optimize`, { prompt });
  return response.data as PromptOptimizeResult;
}

export async function listPromptTemplates(): Promise<{ items: PromptTemplate[] }> {
  const response = await http.get("/v1/prompt-templates");
  return response.data;
}

export async function listSkillCatalog(): Promise<{ items: SkillRecord[] }> {
  const response = await http.get("/v1/skills/catalog");
  return response.data;
}

export async function listAgentSkills(agentInstanceId: string): Promise<{ config_version_id: string; items: SkillRecord[] }> {
  const response = await http.get(`/v1/agent-instances/${agentInstanceId}/skills`);
  return response.data;
}


export type KnowledgeDocument = { document_id: string; title: string; filename: string; source: string; status: string };

export async function listAgentKnowledge(agentInstanceId: string): Promise<{ config_version_id: string; selected_document_ids: string[]; items: KnowledgeDocument[] }> {
  const response = await http.get(`/v1/agent-instances/${agentInstanceId}/knowledge`);
  return response.data;
}

export const KNOWLEDGE_UPLOAD_ACCEPT = ".md,.txt";
export const MAX_KNOWLEDGE_UPLOAD_BYTES = 1 * 1024 * 1024;

export function isAllowedKnowledgeFilename(filename: string): boolean {
  const name = String(filename || "").trim().toLowerCase();
  return name.endsWith(".md") || name.endsWith(".txt");
}

export function isKnowledgeApiMissing(error: unknown): boolean {
  if (!error || typeof error !== "object") return false;
  const status = (error as { response?: { status?: number } }).response?.status;
  return status === 404;
}

export async function uploadAgentKnowledge(agentInstanceId: string, file: File, title?: string): Promise<KnowledgeDocument> {
  const form = new FormData();
  form.append("file", file);
  const trimmed = String(title || "").trim();
  if (trimmed) form.append("title", trimmed);
  const response = await http.post(`/v1/agent-instances/${agentInstanceId}/knowledge`, form);
  return response.data as KnowledgeDocument;
}

export async function updateAgentSkills(agentInstanceId: string, skillIds: string[]) {
  const response = await http.put(`/v1/agent-instances/${agentInstanceId}/config/draft/skills`, { skill_ids: skillIds });
  return response.data as { config_version_id: string; items: SkillRecord[] };
}

export type AgentSkillWrite = {
  name: string;
  description?: string;
  instructions?: string;
  risk_level?: string;
  approval_mode?: string;
};

export async function createAgentSkill(agentInstanceId: string, payload: AgentSkillWrite): Promise<SkillRecord> {
  const response = await http.post(`/v1/agent-instances/${agentInstanceId}/skills`, payload);
  return response.data as SkillRecord;
}

export async function patchAgentSkill(
  agentInstanceId: string,
  skillId: string,
  payload: Partial<AgentSkillWrite> & { enabled?: boolean },
): Promise<{ config_version_id: string; items: SkillRecord[] }> {
  const response = await http.patch(`/v1/agent-instances/${agentInstanceId}/skills/${skillId}`, payload);
  return response.data;
}

export async function searchSkills(query: string, limit = 10) {
  const response = await http.post("/v1/skills/discovery/search", { query, limit });
  return response.data as { items: Array<Record<string, unknown>> };
}

export async function startSkillImport(agentInstanceId: string, candidateId: string): Promise<SkillImport> {
  const response = await http.post(`/v1/skills/imports?agent_instance_id=${encodeURIComponent(agentInstanceId)}`, { candidate_id: candidateId });
  return response.data;
}

export async function confirmSkillImport(importId: string): Promise<SkillRecord> {
  const response = await http.post(`/v1/skills/imports/${importId}/confirm`);
  return response.data;
}

export async function rejectSkillImport(importId: string): Promise<SkillImport> {
  const response = await http.post(`/v1/skills/imports/${importId}/reject`);
  return response.data;
}

export async function listApprovals(agentInstanceId: string, configVersionId?: string): Promise<{ items: ApprovalRecord[] }> {
  const params = configVersionId ? { config_version_id: configVersionId } : undefined;
  const response = await http.get(`/v1/agent-instances/${agentInstanceId}/approvals`, { params });
  return response.data;
}

export async function requestApproval(
  agentInstanceId: string,
  payload: Pick<ApprovalRecord, "thread_id" | "config_version_id" | "approval_kind" | "resource_code">,
): Promise<ApprovalRecord> {
  const response = await http.post(`/v1/agent-instances/${agentInstanceId}/approvals`, payload);
  return response.data;
}

export async function decideApproval(approvalId: string, approved: boolean, reason = ""): Promise<ApprovalRecord> {
  const response = await http.post(`/v1/approvals/${approvalId}/decision`, { approved, reason });
  return response.data;
}

export async function previewAgentDraft(agentInstanceId: string, prompt: string) {
  const response = await http.post(`/v1/agent-instances/${agentInstanceId}/config/draft/preview`, { prompt });
  return response.data as { config_version_id: string; status: string; answer: string; enabled_tool_codes: string[]; knowledge_document_ids: string[] };
}

export const BUILTIN_TOOL_CODE = "get_current_datetime";
export const DISCOVER_LEADS_TOOL_CODE = "discover_leads";
const LEGACY_DISCOVER_LEADS_TOOL_CODE = "discover_douyin_leads";

export type ToolCatalogItem = {
  tool_code: string;
  display_name: string;
  description: string;
  risk_level: string;
  enabled: boolean;
  built_in: boolean;
  group: string;
};

export type WorkflowCatalogItem = {
  code: string;
  display_name: string;
  enabled?: boolean;
};

export const pendingWorkflowCodes = reactive<{ codes: string[] | null }>({ codes: null });

export function resolveToolCode(code: string): string {
  const value = String(code || "").trim();
  return value === LEGACY_DISCOVER_LEADS_TOOL_CODE ? DISCOVER_LEADS_TOOL_CODE : value;
}

export function withRequiredDatetime(codes: Iterable<string>): string[] {
  const resolved: string[] = [];
  const seen = new Set<string>();
  for (const raw of codes) {
    const code = resolveToolCode(raw);
    if (!code || seen.has(code)) continue;
    seen.add(code);
    resolved.push(code);
  }
  if (!seen.has(BUILTIN_TOOL_CODE)) resolved.unshift(BUILTIN_TOOL_CODE);
  return resolved;
}

export async function listAgentTools(agentInstanceId: string): Promise<{ config_version_id: string; items: ToolCatalogItem[] }> {
  const response = await http.get(`/v1/agent-instances/${agentInstanceId}/tools`);
  return response.data;
}

export async function updateAgentTools(agentInstanceId: string, enabledToolCodes: string[]): Promise<AgentConfig> {
  const response = await http.put(`/v1/agent-instances/${agentInstanceId}/config/draft/tools`, {
    enabled_tool_codes: withRequiredDatetime(enabledToolCodes),
  });
  return response.data;
}
