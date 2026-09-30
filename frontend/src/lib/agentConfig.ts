export const EDITOR_SECTIONS = [
  { id: "model", label: "模型设置" },
  { id: "prompt", label: "提示词" },
  { id: "welcome", label: "欢迎语" },
  { id: "examples", label: "示例问题" },
  { id: "knowledge", label: "知识库" },
  { id: "workflow", label: "工作流" },
  { id: "tools", label: "工具与工作流" },
  { id: "skills", label: "Skills" },
  { id: "experience", label: "经验" },
  { id: "memory", label: "记忆" },
  { id: "versions", label: "版本" },
  { id: "approvals", label: "审批状态" },
] as const;

export type EditorSectionId = (typeof EDITOR_SECTIONS)[number]["id"];

export const PLACEHOLDER_SECTION_IDS = ["workflow", "experience", "memory", "versions"] as const;

export const EDITOR_TOOL_OPTIONS = [
  { code: "get_current_datetime", name: "当前时间", required: true },
  { code: "search_kb", name: "知识库检索", required: false },
  { code: "discover_douyin_leads", name: "抖音线索发现", required: false },
] as const;

export type AgentConfigDraft = {
  system_prompt: string;
  welcome_message: string;
  example_questions: string[];
  enabled_tool_codes: string[];
  workflow_codes: string[];
  knowledge_document_ids: string[];
};

export const APPROVAL_KIND_LABELS: Record<string, string> = {
  import: "导入",
  skill: "Skill 使用",
  script: "Skill 脚本",
  tool: "工具执行",
};

export const RISK_LABELS: Record<string, string> = {
  low: "低风险",
  medium: "中风险",
  high: "高风险",
};

export function normalizeExamples(items: string[]): string[] {
  return items.map((item) => item.trim()).filter(Boolean).slice(0, 10);
}

export function selectedSkillIds(items: Array<{ skill_id: string }>): string[] {
  return items.map((item) => item.skill_id);
}

export function draftSafetyNotice(): string {
  return "一键优化只生成草稿文本。确认保存前不会修改工具白名单、Skill 绑定、风险等级、工作流权限或服务端安全规则。";
}

export function approvalStatusLabel(status: string): string {
  return ({ pending: "待审批", approved: "已批准", rejected: "已拒绝" } as Record<string, string>)[status] || status;
}

export function importStatusLabel(status: string): string {
  return ({ awaiting_confirmation: "扫描完成，等待确认", failed: "扫描失败", confirmed: "已导入", imported: "已导入" } as Record<string, string>)[status] || status;
}

export function scanSummary(report: Record<string, unknown>): string {
  const warnings = Array.isArray(report.warnings)
    ? report.warnings.length
    : Array.isArray((report.manifest as Record<string, unknown> | undefined)?.warnings)
      ? ((report.manifest as Record<string, unknown>).warnings as unknown[]).length
      : 0;
  return `${String(report.risk_level || "unknown")} · warnings ${warnings} · scripts ${Array.isArray(report.script_types) ? report.script_types.join(",") || "none" : "none"}`;
}

export function scanDetails(report: Record<string, unknown>): string {
  const manifest = (report.manifest as Record<string, unknown> | undefined) || {};
  const files = Array.isArray(manifest.files) ? manifest.files.length : Number(report.file_count || 0);
  return `文件 ${files} · ${String(report.total_bytes || 0)} bytes · license ${String(manifest.license || "unknown")}`;
}
