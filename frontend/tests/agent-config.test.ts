import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { enableAutoUnmount, flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  APPROVAL_KIND_LABELS,
  EDITOR_SECTIONS,
  EDITOR_TOOL_OPTIONS,
  PLACEHOLDER_SECTION_IDS,
  approvalStatusLabel,
  draftSafetyNotice,
  importStatusLabel,
  normalizeExamples,
  scanDetails,
  scanSummary,
  selectedSkillIds,
} from "../src/lib/agentConfig";
import { reactive } from "vue";
import PromptSection from "../src/components/agent-config/sections/PromptSection.vue";
import ToolsSection from "../src/components/agent-config/sections/ToolsSection.vue";
import WorkflowSection from "../src/components/agent-config/sections/WorkflowSection.vue";
import SkillsSection from "../src/components/agent-config/sections/SkillsSection.vue";
import WelcomeSection from "../src/components/agent-config/sections/WelcomeSection.vue";
import ExamplesSection from "../src/components/agent-config/sections/ExamplesSection.vue";
import KnowledgeSection from "../src/components/agent-config/sections/KnowledgeSection.vue";
import ExperienceSection from "../src/components/agent-config/sections/ExperienceSection.vue";
import MemorySection from "../src/components/agent-config/sections/MemorySection.vue";
import VersionsSection from "../src/components/agent-config/sections/VersionsSection.vue";
import AgentConfigTopbar from "../src/components/agent-config/AgentConfigTopbar.vue";
import AgentConfigNav from "../src/components/agent-config/AgentConfigNav.vue";
import AgentConfigView from "../src/views/AgentConfigView.vue";
import {
  BUILTIN_TOOL_CODE,
  DISCOVER_LEADS_TOOL_CODE,
  isAllowedKnowledgeFilename,
  isKnowledgeApiMissing,
  pendingWorkflowCodes,
  resolveToolCode,
  withRequiredDatetime,
} from "../src/api/agentConfig";

enableAutoUnmount(afterEach);

const getAgentConfig = vi.fn();
const listPromptTemplates = vi.fn();
const listSkillCatalog = vi.fn();
const listAgentSkills = vi.fn();
const listAgentKnowledge = vi.fn();
const uploadAgentKnowledge = vi.fn();
const listAgentTools = vi.fn();
const updateAgentTools = vi.fn();
const listApprovals = vi.fn();
const updateAgentConfig = vi.fn();
const updateAgentSkills = vi.fn();
const createAgentSkill = vi.fn();
const patchAgentSkill = vi.fn();
const publishAgentConfig = vi.fn();
const optimizeAgentPrompt = vi.fn();
const previewAgentDraft = vi.fn();
const searchSkills = vi.fn();
const startSkillImport = vi.fn();
const confirmSkillImport = vi.fn();
const decideApproval = vi.fn();
const getAgentSidebar = vi.fn();
const listAgentInstances = vi.fn();
const patchAgentInstance = vi.fn();
const httpGet = vi.fn();
const openDebugThread = vi.fn();
const getThread = vi.fn();
const postMessage = vi.fn();
const resumeThread = vi.fn();
const agentCss = readFileSync(resolve(process.cwd(), "src/styles/agent.css"), "utf-8");
const viewSource = readFileSync(resolve(process.cwd(), "src/views/AgentConfigView.vue"), "utf-8");
const toolsSource = readFileSync(resolve(process.cwd(), "src/components/agent-config/sections/ToolsSection.vue"), "utf-8");

vi.mock("../src/api/agents", () => ({
  getAgentSidebar: (...args: unknown[]) => getAgentSidebar(...args),
  listAgentInstances: (...args: unknown[]) => listAgentInstances(...args),
  patchAgentInstance: (...args: unknown[]) => patchAgentInstance(...args),
}));

vi.mock("../src/api/agentConfig", async () => {
  const actual = await vi.importActual<typeof import("../src/api/agentConfig")>("../src/api/agentConfig");
  return {
    ...actual,
    getAgentConfig: (...args: unknown[]) => getAgentConfig(...args),
    listPromptTemplates: (...args: unknown[]) => listPromptTemplates(...args),
    listSkillCatalog: (...args: unknown[]) => listSkillCatalog(...args),
    listAgentSkills: (...args: unknown[]) => listAgentSkills(...args),
    listAgentKnowledge: (...args: unknown[]) => listAgentKnowledge(...args),
    uploadAgentKnowledge: (...args: unknown[]) => uploadAgentKnowledge(...args),
    listAgentTools: (...args: unknown[]) => listAgentTools(...args),
    updateAgentTools: (...args: unknown[]) => updateAgentTools(...args),
    listApprovals: (...args: unknown[]) => listApprovals(...args),
    updateAgentConfig: (...args: unknown[]) => updateAgentConfig(...args),
    updateAgentSkills: (...args: unknown[]) => updateAgentSkills(...args),
    createAgentSkill: (...args: unknown[]) => createAgentSkill(...args),
    patchAgentSkill: (...args: unknown[]) => patchAgentSkill(...args),
    publishAgentConfig: (...args: unknown[]) => publishAgentConfig(...args),
    optimizeAgentPrompt: (...args: unknown[]) => optimizeAgentPrompt(...args),
    previewAgentDraft: (...args: unknown[]) => previewAgentDraft(...args),
    searchSkills: (...args: unknown[]) => searchSkills(...args),
    startSkillImport: (...args: unknown[]) => startSkillImport(...args),
    confirmSkillImport: (...args: unknown[]) => confirmSkillImport(...args),
    decideApproval: (...args: unknown[]) => decideApproval(...args),
  };
});

vi.mock("vue-router", async () => {
  const actual = await vi.importActual<typeof import("vue-router")>("vue-router");
  return {
    ...actual,
    useRoute: () => ({ params: { agentInstanceId: "id-1" }, query: {} }),
    useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  };
});

vi.mock("../src/api/http", async () => {
  const actual = await vi.importActual<typeof import("../src/api/http")>("../src/api/http");
  return {
    ...actual,
    http: {
      get: (...args: unknown[]) => httpGet(...args),
    },
  };
});

vi.mock("../src/api/threads", () => ({
  getThread: (...args: unknown[]) => getThread(...args),
  postMessage: (...args: unknown[]) => postMessage(...args),
  resumeThread: (...args: unknown[]) => resumeThread(...args),
  openDebugThread: (...args: unknown[]) => openDebugThread(...args),
}));

const defaultToolCatalog = {
  config_version_id: "cfg-1",
  items: [
    { tool_code: "get_current_datetime", display_name: "当前时间", description: "获取当前日期和时间。", risk_level: "low", enabled: true, built_in: true, group: "builtin" },
    { tool_code: "search_kb", display_name: "知识库检索", description: "检索当前智能体实例知识库。", risk_level: "low", enabled: false, built_in: false, group: "knowledge" },
    { tool_code: "discover_leads", display_name: "线索发现", description: "扫描抖音或小红书线索。", risk_level: "high", enabled: false, built_in: false, group: "leads" },
  ],
};

beforeEach(() => {
  pendingWorkflowCodes.codes = null;
  httpGet.mockReset();
  httpGet.mockResolvedValue({ data: { items: [] } });
  openDebugThread.mockReset();
  getThread.mockReset();
  postMessage.mockReset();
  resumeThread.mockReset();
  decideApproval.mockReset();
  decideApproval.mockResolvedValue({ approval_id: "appr-1", status: "approved" });
  resumeThread.mockResolvedValue({ thread_id: "dbg-1", thread_kind: "debug", status: "idle", interrupt: null, messages: [] });
  openDebugThread.mockResolvedValue({
    agent_instance_id: "id-1",
    thread_id: "dbg-1",
    thread_kind: "debug",
    config_version_id: "cfg-1",
  });
  getThread.mockResolvedValue({ thread_id: "dbg-1", thread_kind: "debug", messages: [] });
  postMessage.mockResolvedValue({
    thread_id: "dbg-1",
    thread_kind: "debug",
    messages: [
      { role: "user", content: "preview-hi" },
      { role: "assistant", content: "debug-sse-ok" },
    ],
  });
  listAgentTools.mockResolvedValue(defaultToolCatalog);
  uploadAgentKnowledge.mockReset();
  updateAgentTools.mockResolvedValue({
    config_version_id: "cfg-1",
    user_id: "u1",
    agent_instance_id: "id-1",
    version_no: 1,
    status: "draft",
    system_prompt: "你是客服",
    welcome_message: "你好",
    example_questions: ["如何退款"],
    enabled_tool_codes: ["get_current_datetime"],
    workflow_codes: [],
    knowledge_document_ids: [],
  });
});

describe("agent config helpers", () => {
  it("normalizes draft examples without changing the tool or skill policy", () => {
    expect(normalizeExamples(["  你好  ", "", "如何退款"])).toEqual(["你好", "如何退款"]);
    expect(draftSafetyNotice()).toContain("不会修改工具白名单");
    expect(draftSafetyNotice()).toContain("Skill 绑定");
  });

  it("keeps selected skills as explicit ids", () => {
    expect(selectedSkillIds([{ skill_id: "a" }, { skill_id: "b" }])).toEqual(["a", "b"]);
  });

  it("labels all independent approval kinds", () => {
    expect(Object.keys(APPROVAL_KIND_LABELS)).toEqual(["import", "skill", "script", "tool"]);
    expect(approvalStatusLabel("pending")).toBe("待审批");
    expect(importStatusLabel("awaiting_confirmation")).toBe("扫描完成，等待确认");
  });

  it("keeps editor sections and placeholder ids for later windows", () => {
    expect(EDITOR_SECTIONS.map((item) => item.id)).toEqual([
      "model",
      "prompt",
      "welcome",
      "examples",
      "knowledge",
      "workflow",
      "tools",
      "skills",
      "experience",
      "memory",
      "versions",
      "approvals",
    ]);
    expect([...PLACEHOLDER_SECTION_IDS]).toEqual(["workflow", "experience", "memory", "versions"]);
  });

  it("resolves legacy discover_douyin_leads to discover_leads and keeps datetime required", () => {
    expect(resolveToolCode("discover_douyin_leads")).toBe(DISCOVER_LEADS_TOOL_CODE);
    expect(resolveToolCode("discover_leads")).toBe("discover_leads");
    expect(BUILTIN_TOOL_CODE).toBe("get_current_datetime");
    expect(withRequiredDatetime(["search_kb"])).toEqual(["get_current_datetime", "search_kb"]);
    expect(withRequiredDatetime(["discover_douyin_leads"])).toEqual(["get_current_datetime", "discover_leads"]);
    expect(EDITOR_TOOL_OPTIONS.map((item) => item.code)).toContain("discover_douyin_leads");
  });

  it("summarizes skill scan reports without changing risk policy", () => {
    expect(scanSummary({ risk_level: "low", warnings: [1], script_types: ["python"] })).toBe("low · warnings 1 · scripts python");
    expect(scanDetails({ total_bytes: 12, manifest: { files: ["a"], license: "MIT" } })).toBe("文件 1 · 12 bytes · license MIT");
  });
});

describe("agent config view shell", () => {
  beforeEach(() => {
    getAgentConfig.mockResolvedValue({
      config_version_id: "cfg-1",
      user_id: "u1",
      agent_instance_id: "id-1",
      version_no: 1,
      status: "draft",
      system_prompt: "你是客服",
      welcome_message: "你好",
      example_questions: ["如何退款"],
      enabled_tool_codes: ["get_current_datetime"],
      workflow_codes: ["douyin-lead-discovery"],
      knowledge_document_ids: [],
    });
    listPromptTemplates.mockResolvedValue({ items: [{ template_id: "t1", name: "客服模板", description: "", prompt: "模板提示词", variables: [], tool_codes: [], skill_codes: [] }] });
    listSkillCatalog.mockResolvedValue({ items: [] });
    listAgentSkills.mockResolvedValue({ config_version_id: "cfg-1", items: [] });
    listAgentKnowledge.mockResolvedValue({ config_version_id: "cfg-1", selected_document_ids: [], items: [] });
    listApprovals.mockResolvedValue({ items: [] });
    getAgentSidebar.mockResolvedValue({ title: "助手A", intro: "客服简介" });
    listAgentInstances.mockResolvedValue({
      items: [{ agent_instance_id: "id-1", title: "助手A", intro: "客服简介", template_code: "custom" }],
    });
    patchAgentInstance.mockResolvedValue({ agent_instance_id: "id-1", title: "助手A", intro: "客服简介" });
    previewAgentDraft.mockResolvedValue({ config_version_id: "cfg-1", status: "draft", answer: "假预览答案", enabled_tool_codes: [], knowledge_document_ids: [] });
  });

  it("assembles topbar nav sections and draft debug pane", async () => {
    const wrapper = mount(AgentConfigView);
    await flushPromises();
    expect(wrapper.text()).toContain("智能体编辑");
    expect(wrapper.text()).toContain("保存草稿");
    expect(wrapper.text()).toContain("发布配置");
    expect(wrapper.text()).toContain("草稿配置");
    expect(wrapper.text()).toContain("配置边界");
    expect(wrapper.text()).toContain("调试环境");
    expect(wrapper.get(".agent-editor-preview .agent-btn").text()).toBe("发送");
    expect(wrapper.find(".agent-editor-preview").text()).toContain("使用未发布草稿");
    expect(wrapper.text()).toContain("工作流");
    expect(wrapper.text()).toContain("经验");
    expect(wrapper.text()).toContain("记忆");
    expect(wrapper.text()).toContain("版本");
    expect(wrapper.findComponent({ name: "AgentConfigTopbar" }).exists() || wrapper.find(".agent-editor-topbar").exists()).toBe(true);
    expect(wrapper.find(".agent-editor-nav").exists()).toBe(true);
    expect(wrapper.find(".agent-editor-preview").exists()).toBe(true);
  });

  it("opens a debug thread and sends via real SSE instead of fake preview", async () => {
    previewAgentDraft.mockClear();
    const wrapper = mount(AgentConfigView);
    await flushPromises();
    expect(openDebugThread).toHaveBeenCalledWith("id-1");
    await wrapper.get(".agent-editor-preview textarea").setValue("预览一句");
    await wrapper.get(".agent-editor-preview .agent-btn").trigger("click");
    await flushPromises();
    expect(postMessage).toHaveBeenCalledWith("dbg-1", "预览一句", expect.any(String), expect.any(Object));
    expect(previewAgentDraft).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain("debug-sse-ok");
    expect(wrapper.text()).not.toContain("不会创建正式线程");
    expect(wrapper.text()).not.toContain("不会执行工具");
    expect(wrapper.text()).not.toContain("假预览答案");
  });

  it("loads tools from catalog with locked datetime and empty custom workflows", async () => {
    const wrapper = mount(AgentConfigView);
    await flushPromises();
    const navButtons = wrapper.findAll(".agent-editor-nav-item");
    await navButtons.find((btn) => btn.text() === "工具与工作流")!.trigger("click");
    expect(wrapper.text()).toContain("当前时间");
    expect(wrapper.text()).toContain("知识库检索");
    expect(wrapper.text()).toContain("线索发现");
    expect(wrapper.text()).toContain("discover_leads");
    expect(wrapper.text()).not.toContain("discover_douyin_leads");
    expect(wrapper.text()).not.toContain("抖音线索发现");
    const datetimeRow = wrapper.findAll(".agent-tool-row").find((row) => row.text().includes("当前时间"));
    expect(datetimeRow).toBeTruthy();
    expect(datetimeRow!.get("input").attributes("disabled")).toBeDefined();
    await navButtons.find((btn) => btn.text() === "工作流")!.trigger("click");
    expect(wrapper.text()).toContain("当前模板没有可勾选的工作流");
    expect(wrapper.text()).not.toContain("现有工作流代码仍在「工具与工作流」中编辑");
    expect(wrapper.find(".agent-workflow-empty").exists()).toBe(true);
    await navButtons.find((btn) => btn.text() === "经验")!.trigger("click");
    expect(wrapper.text()).toContain("开场体验");
  });

  it("freezes AgentConfigView as an assembly shell", () => {
    expect(viewSource).toContain("AgentConfigTopbar");
    expect(viewSource).toContain("AgentConfigNav");
    expect(viewSource).toContain("AgentConfigDebugPane");
    expect(viewSource).toContain("ModelSection");
    expect(viewSource).toContain("WorkflowSection");
    expect(viewSource).toContain("ExperienceSection");
    expect(viewSource).toContain("MemorySection");
    expect(viewSource).toContain("VersionsSection");
    expect(viewSource).not.toContain("discover_douyin_leads");
    expect(viewSource).not.toContain("一键优化");
    expect(toolsSource).not.toContain("EDITOR_TOOL_OPTIONS");
    expect(toolsSource).not.toContain("discover_douyin_leads");
    expect(toolsSource).toContain("listAgentTools");
    expect(toolsSource).toContain("discover_leads");
    expect(readFileSync(resolve(process.cwd(), "src/lib/agentConfig.ts"), "utf-8")).toContain("discover_douyin_leads");
    expect(agentCss).toMatch(/\.agent-section-placeholder[\s\S]*line-height: 1\.6;/);
    expect(agentCss.lastIndexOf(".agent-section-placeholder")).toBeGreaterThan(agentCss.lastIndexOf(".agent-editor-loading"));
    expect(agentCss).toContain(".agent-workflow-empty");
    expect(agentCss.lastIndexOf(".agent-workflow-empty")).toBeGreaterThan(agentCss.lastIndexOf(".agent-prompt-mode"));
  });
});

describe("agent config model section", () => {
  beforeEach(() => {
    getAgentConfig.mockResolvedValue({
      config_version_id: "cfg-1",
      user_id: "u1",
      agent_instance_id: "id-1",
      version_no: 1,
      status: "draft",
      system_prompt: "你是客服",
      welcome_message: "你好",
      example_questions: ["如何退款"],
      enabled_tool_codes: ["get_current_datetime"],
      workflow_codes: ["douyin-lead-discovery"],
      knowledge_document_ids: [],
    });
    listPromptTemplates.mockResolvedValue({ items: [] });
    listSkillCatalog.mockResolvedValue({ items: [] });
    listAgentSkills.mockResolvedValue({ config_version_id: "cfg-1", items: [] });
    listAgentKnowledge.mockResolvedValue({ config_version_id: "cfg-1", selected_document_ids: [], items: [] });
    listApprovals.mockResolvedValue({ items: [] });
    getAgentSidebar.mockResolvedValue({ title: "助手A", intro: "客服简介" });
    listAgentInstances.mockResolvedValue({
      items: [{ agent_instance_id: "id-1", title: "助手A", intro: "客服简介", template_code: "custom" }],
    });
    patchAgentInstance.mockResolvedValue({ agent_instance_id: "id-1", title: "新助手A", intro: "新的简介" });
    previewAgentDraft.mockResolvedValue({ config_version_id: "cfg-1", status: "draft", answer: "假预览答案", enabled_tool_codes: [], knowledge_document_ids: [] });
  });

  it("shows instance basics, custom template tag, readonly model copy, and draft notice", async () => {
    const wrapper = mount(AgentConfigView);
    await flushPromises();
    const navButtons = wrapper.findAll(".agent-editor-nav-item");
    await navButtons.find((btn) => btn.text() === "模型设置")!.trigger("click");
    expect(wrapper.text()).toContain("当前编辑的是 draft");
    expect(wrapper.text()).toContain("自定义智能体");
    expect(wrapper.get(".agent-model-title").element).toHaveProperty("value", "助手A");
    expect(wrapper.get(".agent-model-intro").element).toHaveProperty("value", "客服简介");
    expect(wrapper.get(".agent-model-name").element).toHaveProperty("value", "服务端默认对话模型");
    expect(wrapper.get(".agent-model-name").attributes("disabled")).toBeDefined();
    expect(wrapper.find(".agent-model-section select").exists()).toBe(false);
    expect(wrapper.text()).toContain("不提供模型下拉或切换");
  });

  it("labels 运营助手 when the instance template is douyin_ops", async () => {
    listAgentInstances.mockResolvedValue({
      items: [{ agent_instance_id: "id-1", title: "助手A", intro: "客服简介", template_code: "douyin_ops" }],
    });
    const wrapper = mount(AgentConfigView);
    await flushPromises();
    expect(wrapper.find(".agent-model-template").text()).toBe("运营助手");
    expect(wrapper.find(".agent-model-template").classes()).toContain("is-ops");
  });

  it("saves name and intro through the existing instance PATCH API", async () => {
    const wrapper = mount(AgentConfigView);
    await flushPromises();
    await wrapper.get(".agent-model-title").setValue("新助手A");
    await wrapper.get(".agent-model-intro").setValue("新的简介");
    await wrapper.get(".agent-model-save").trigger("click");
    await flushPromises();
    expect(patchAgentInstance).toHaveBeenCalledWith("id-1", { title: "新助手A", intro: "新的简介" });
    expect(wrapper.text()).toContain("已保存");
  });
});

describe("prompt section dual mode", () => {
  const templates = [
    {
      template_id: "t1",
      name: "客服模板",
      description: "售前售后",
      prompt: "角色：品牌客服\n目标：解答订单问题\n规则：不承诺未核实退款",
      variables: ["brand_name"],
      tool_codes: ["search_kb"],
      skill_codes: [],
    },
  ];

  function makeDraft(systemPrompt = "你是客服") {
    return reactive({
      system_prompt: systemPrompt,
      welcome_message: "",
      example_questions: [],
      enabled_tool_codes: ["get_current_datetime"],
      workflow_codes: [],
      knowledge_document_ids: [],
    });
  }

  it("splits structured fields and joins them back into system_prompt", async () => {
    const draft = makeDraft("你是客服");
    const wrapper = mount(PromptSection, {
      props: { draft, templates, optimizing: false, optimization: null },
    });
    await wrapper.get('[data-prompt-mode="structured"]').trigger("click");
    expect((wrapper.get('[data-prompt-field="role"]').element as HTMLTextAreaElement).value).toBe("你是客服");
    await wrapper.get('[data-prompt-field="role"]').setValue("品牌客服");
    await wrapper.get('[data-prompt-field="goal"]').setValue("回答售后问题");
    await wrapper.get('[data-prompt-field="boundary"]').setValue("不承诺未核实退款");
    await wrapper.get('[data-prompt-field="failure"]').setValue("知识库不足时明确说明");
    expect(draft.system_prompt).toContain("角色：品牌客服");
    expect(draft.system_prompt).toContain("目标：回答售后问题");
    expect(draft.system_prompt).toContain("边界：不承诺未核实退款");
    expect(draft.system_prompt).toContain("失败处理：知识库不足时明确说明");
    await wrapper.get('[data-prompt-mode="plain"]').trigger("click");
    expect((wrapper.get(".agent-prompt-editor").element as HTMLTextAreaElement).value).toBe(draft.system_prompt);
  });

  it("fills a prompt template into the draft text only", async () => {
    const draft = makeDraft("");
    const wrapper = mount(PromptSection, {
      props: { draft, templates, optimizing: false, optimization: null },
    });
    await wrapper.get(".agent-template-chip").trigger("click");
    expect(wrapper.emitted("applyTemplate")?.[0]?.[0]).toEqual(templates[0]);
    draft.system_prompt = templates[0].prompt;
    await wrapper.vm.$nextTick();
    expect((wrapper.get(".agent-prompt-editor").element as HTMLTextAreaElement).value).toBe(templates[0].prompt);
    expect(draft.enabled_tool_codes).toEqual(["get_current_datetime"]);
  });

  it("compares optimize result, writes only after confirm, and can undo", async () => {
    const draft = makeDraft("你是客服");
    const wrapper = mount(PromptSection, {
      props: {
        draft,
        templates,
        optimizing: false,
        optimization: {
          original_prompt: "你是客服",
          optimized_prompt: "你是客服\n\n执行要求：先澄清目标和边界。",
          change_summary: "补充目标、边界、失败处理",
          risk_notice: "确认前不会改变 draft",
        },
      },
    });
    expect(wrapper.text()).toContain("原文");
    expect(wrapper.text()).toContain("优化结果");
    expect(wrapper.text()).toContain("补充目标、边界、失败处理");
    expect(wrapper.text()).toContain("确认前不会改变 draft");
    expect(draft.system_prompt).toBe("你是客服");
    await wrapper.get(".agent-prompt-accept-btn").trigger("click");
    expect(wrapper.emitted("acceptOptimization")).toBeTruthy();
    draft.system_prompt = "你是客服\n\n执行要求：先澄清目标和边界。";
    await wrapper.vm.$nextTick();
    await wrapper.get(".agent-prompt-undo-btn").trigger("click");
    expect(draft.system_prompt).toBe("你是客服");
  });
});

describe("agent config prompt optimize flow", () => {
  beforeEach(() => {
    getAgentConfig.mockResolvedValue({
      config_version_id: "cfg-1",
      user_id: "u1",
      agent_instance_id: "id-1",
      version_no: 1,
      status: "draft",
      system_prompt: "你是客服",
      welcome_message: "你好",
      example_questions: ["如何退款"],
      enabled_tool_codes: ["get_current_datetime"],
      workflow_codes: ["douyin-lead-discovery"],
      knowledge_document_ids: [],
    });
    listPromptTemplates.mockResolvedValue({
      items: [{ template_id: "t1", name: "客服模板", description: "售前售后", prompt: "模板提示词", variables: ["brand_name"], tool_codes: [], skill_codes: [] }],
    });
    listSkillCatalog.mockResolvedValue({ items: [] });
    listAgentSkills.mockResolvedValue({ config_version_id: "cfg-1", items: [] });
    listAgentKnowledge.mockResolvedValue({ config_version_id: "cfg-1", selected_document_ids: [], items: [] });
    listApprovals.mockResolvedValue({ items: [] });
    getAgentSidebar.mockResolvedValue({ title: "助手A", intro: "客服简介" });
    listAgentInstances.mockResolvedValue({
      items: [{ agent_instance_id: "id-1", title: "助手A", intro: "客服简介", template_code: "custom" }],
    });
    patchAgentInstance.mockResolvedValue({ agent_instance_id: "id-1", title: "助手A", intro: "客服简介" });
    optimizeAgentPrompt.mockResolvedValue({
      original_prompt: "你是客服",
      optimized_prompt: "你是客服\n\n执行要求：先澄清目标和边界。",
      change_summary: "补充目标、边界、失败处理",
      risk_notice: "确认前不会改变 draft",
    });
  });

  it("applies a catalog template and optimizes prompt text without touching tools or skills", async () => {
    const wrapper = mount(AgentConfigView);
    await flushPromises();
    await wrapper.get(".agent-template-chip").trigger("click");
    expect((wrapper.get(".agent-prompt-editor").element as HTMLTextAreaElement).value).toBe("模板提示词");
    await wrapper.get(".agent-prompt-optimize-btn").trigger("click");
    await flushPromises();
    expect(optimizeAgentPrompt).toHaveBeenCalledWith("id-1", "模板提示词");
    expect(optimizeAgentPrompt.mock.calls[0]).toHaveLength(2);
    expect(updateAgentSkills).not.toHaveBeenCalled();
    expect(updateAgentConfig).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain("原文");
    expect(wrapper.text()).toContain("优化结果");
    expect(wrapper.text()).toContain("补充目标、边界、失败处理");
    expect(wrapper.text()).toContain("确认前不会改变 draft");
    await wrapper.get(".agent-prompt-accept-btn").trigger("click");
    expect((wrapper.get(".agent-prompt-editor").element as HTMLTextAreaElement).value).toBe("你是客服\n\n执行要求：先澄清目标和边界。");
    await wrapper.get(".agent-prompt-undo-btn").trigger("click");
    expect((wrapper.get(".agent-prompt-editor").element as HTMLTextAreaElement).value).toBe("模板提示词");
  });

  it("keeps prompt dual-mode styles appended after the section shell", () => {
    const promptSource = readFileSync(resolve(process.cwd(), "src/components/agent-config/sections/PromptSection.vue"), "utf-8");
    expect(promptSource).toContain("data-prompt-mode");
    expect(promptSource).toContain("撤销优化");
    expect(agentCss).toContain(".agent-prompt-mode");
    expect(agentCss).toContain(".agent-prompt-compare-grid");
    expect(agentCss.lastIndexOf(".agent-prompt-mode")).toBeGreaterThan(agentCss.lastIndexOf(".agent-section-placeholder"));
  });
});

describe("agent config tools and workflow sections", () => {
  function makeDraft(enabled: string[] = ["get_current_datetime"], workflows: string[] = []) {
    return reactive({
      system_prompt: "",
      welcome_message: "",
      example_questions: [],
      enabled_tool_codes: enabled,
      workflow_codes: workflows,
      knowledge_document_ids: [],
    });
  }

  it("renders catalog tools, keeps datetime locked, and writes discover_leads on toggle", async () => {
    const draft = makeDraft(["get_current_datetime", "discover_douyin_leads"]);
    const wrapper = mount(ToolsSection, { props: { draft } });
    await flushPromises();
    expect(listAgentTools).toHaveBeenCalledWith("id-1");
    expect(wrapper.text()).toContain("当前时间");
    expect(wrapper.text()).toContain("知识库检索");
    expect(wrapper.text()).toContain("线索发现");
    expect(wrapper.text()).toContain("discover_leads");
    expect(wrapper.text()).not.toContain("discover_douyin_leads");
    expect(draft.enabled_tool_codes).toEqual(["get_current_datetime", "discover_leads"]);
    const datetimeInput = wrapper.findAll(".agent-tool-row").find((row) => row.text().includes("当前时间"))!.get("input");
    expect(datetimeInput.attributes("disabled")).toBeDefined();
    draft.enabled_tool_codes = ["get_current_datetime"];
    await wrapper.vm.$nextTick();
    const leadInput = wrapper.findAll(".agent-tool-row").find((row) => row.text().includes("线索发现"))!.get("input");
    expect((leadInput.element as HTMLInputElement).checked).toBe(false);
    await leadInput.setValue(true);
    await leadInput.trigger("change");
    await flushPromises();
    expect(draft.enabled_tool_codes).toContain("discover_leads");
    expect(draft.enabled_tool_codes).toContain("get_current_datetime");
    expect(draft.enabled_tool_codes).not.toContain("discover_douyin_leads");
    expect(updateAgentTools).toHaveBeenCalledWith("id-1", expect.arrayContaining(["get_current_datetime", "discover_leads"]));
  });

  it("shows empty workflow catalog for custom and does not bind Dify", async () => {
    getAgentSidebar.mockResolvedValue({ title: "助手A", intro: "客服简介", workflows: [] });
    const wrapper = mount(WorkflowSection);
    await flushPromises();
    expect(wrapper.find(".agent-workflow-empty").exists()).toBe(true);
    expect(wrapper.text()).toContain("当前模板没有可勾选的工作流");
    expect(wrapper.text()).toContain("默认不绑定 Dify");
    expect(pendingWorkflowCodes.codes).toEqual([]);
  });

  it("toggles template workflow codes from sidebar catalog into pending draft state", async () => {
    getAgentSidebar.mockResolvedValue({
      title: "运营助手",
      workflows: [{ code: "douyin-lead-discovery", display_name: "线索发现与触达", enabled: true }],
    });
    pendingWorkflowCodes.codes = ["douyin-lead-discovery"];
    const wrapper = mount(WorkflowSection);
    await flushPromises();
    expect(wrapper.find(".agent-workflow-empty").exists()).toBe(false);
    expect(wrapper.text()).toContain("线索发现与触达");
    expect(wrapper.text()).toContain("douyin-lead-discovery");
    const box = wrapper.get(".agent-tool-row input");
    expect((box.element as HTMLInputElement).checked).toBe(true);
    await box.setValue(false);
    expect(pendingWorkflowCodes.codes).toEqual([]);
    await box.setValue(true);
    expect(pendingWorkflowCodes.codes).toEqual(["douyin-lead-discovery"]);
  });
});


describe("agent config welcome examples knowledge", () => {
  function makeDraft(overrides: Record<string, unknown> = {}) {
    return reactive({
      system_prompt: "",
      welcome_message: "你好",
      example_questions: ["如何退款"],
      enabled_tool_codes: ["get_current_datetime"],
      workflow_codes: [],
      knowledge_document_ids: [],
      ...overrides,
    });
  }

  it("writes welcome_message into the draft textarea and can persist it", async () => {
    updateAgentConfig.mockResolvedValue({ welcome_message: "欢迎光临" });
    const draft = makeDraft();
    const wrapper = mount(WelcomeSection, { props: { draft } });
    const editor = wrapper.get(".agent-welcome-editor");
    expect((editor.element as HTMLTextAreaElement).value).toBe("你好");
    await editor.setValue("欢迎光临");
    expect(draft.welcome_message).toBe("欢迎光临");
    await wrapper.get(".agent-welcome-save").trigger("click");
    await flushPromises();
    expect(updateAgentConfig).toHaveBeenCalledWith("id-1", { welcome_message: "欢迎光临" });
  });

  it("adds and removes example questions and blocks the 11th item", async () => {
    updateAgentConfig.mockResolvedValue({ example_questions: [] });
    const draft = makeDraft({ example_questions: ["一", "二"] });
    const wrapper = mount(ExamplesSection, { props: { draft } });
    expect(wrapper.findAll(".agent-example-row")).toHaveLength(2);
    await wrapper.get(".agent-example-add").trigger("click");
    expect(draft.example_questions).toHaveLength(3);
    expect(draft.example_questions[2]).toBe("");
    await wrapper.get(".agent-example-remove").trigger("click");
    expect(draft.example_questions).toHaveLength(2);
    draft.example_questions.splice(0, draft.example_questions.length, ...Array.from({ length: 10 }, (_, index) => `q${index}`));
    await wrapper.vm.$nextTick();
    expect(wrapper.get(".agent-example-add").attributes("disabled")).toBeDefined();
    await wrapper.get(".agent-example-add").trigger("click");
    expect(draft.example_questions).toHaveLength(10);
    await wrapper.get(".agent-example-save").trigger("click");
    await flushPromises();
    expect(updateAgentConfig).toHaveBeenCalledWith("id-1", { example_questions: draft.example_questions });
  });

  it("lists instance documents, toggles draft knowledge ids, and uploads md/txt", async () => {
    const documents = [
      { document_id: "doc-1", title: "退款说明", filename: "refund.md", source: "user_upload", status: "ready" },
      { document_id: "doc-2", title: "处理中", filename: "pending.txt", source: "user_upload", status: "uploaded" },
    ];
    listAgentKnowledge.mockResolvedValue({ config_version_id: "cfg-1", selected_document_ids: ["doc-1"], items: documents });
    uploadAgentKnowledge.mockResolvedValue({
      document_id: "doc-3",
      title: "faq",
      filename: "faq.md",
      source: "user_upload",
      status: "ready",
    });
    updateAgentConfig.mockResolvedValue({ knowledge_document_ids: ["doc-1"] });
    const draft = makeDraft({ knowledge_document_ids: [] });
    const wrapper = mount(KnowledgeSection, { props: { draft, documents: [] } });
    await flushPromises();
    expect(listAgentKnowledge).toHaveBeenCalledWith("id-1");
    expect(wrapper.text()).toContain("退款说明");
    expect(wrapper.text()).toContain("refund.md");
    expect(draft.knowledge_document_ids).toEqual(["doc-1"]);
    const pending = wrapper.findAll(".agent-knowledge-row").find((row) => row.text().includes("处理中"))!;
    expect(pending.get("input").attributes("disabled")).toBeDefined();
    const ready = wrapper.findAll(".agent-knowledge-row").find((row) => row.text().includes("退款说明"))!;
    await ready.get("input").setValue(false);
    await flushPromises();
    expect(draft.knowledge_document_ids).not.toContain("doc-1");
    expect(updateAgentConfig).toHaveBeenCalledWith("id-1", { knowledge_document_ids: [] });

    const input = wrapper.get(".agent-knowledge-file");
    const file = new File(["# faq"], "faq.md", { type: "text/markdown" });
    Object.defineProperty(input.element, "files", { value: [file], configurable: true });
    await input.trigger("change");
    await flushPromises();
    expect(uploadAgentKnowledge).toHaveBeenCalledWith("id-1", file);
    expect(draft.knowledge_document_ids).toContain("doc-3");
    expect(wrapper.text()).toContain("faq.md");
  });

  it("rejects non md/txt locally and keeps editing when upload returns 404", async () => {
    listAgentKnowledge.mockResolvedValue({ config_version_id: "cfg-1", selected_document_ids: [], items: [] });
    uploadAgentKnowledge.mockRejectedValue({ response: { status: 404 } });
    const draft = makeDraft({ welcome_message: "仍可编辑" });
    const wrapper = mount(KnowledgeSection, { props: { draft, documents: [] } });
    await flushPromises();
    const input = wrapper.get(".agent-knowledge-file");
    const pdf = new File(["%PDF"], "guide.pdf", { type: "application/pdf" });
    Object.defineProperty(input.element, "files", { value: [pdf], configurable: true });
    await input.trigger("change");
    await flushPromises();
    expect(uploadAgentKnowledge).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain("只支持上传 .md 或 .txt 文件。");

    const md = new File(["hello"], "guide.txt", { type: "text/plain" });
    Object.defineProperty(input.element, "files", { value: [md], configurable: true });
    await input.trigger("change");
    await flushPromises();
    expect(uploadAgentKnowledge).toHaveBeenCalled();
    expect(wrapper.text()).toContain("知识上传接口暂不可用");
    expect(wrapper.text()).toContain("不影响欢迎语、示例等其它表单");
    expect(draft.welcome_message).toBe("仍可编辑");
    expect(isKnowledgeApiMissing({ response: { status: 404 } })).toBe(true);
    expect(isAllowedKnowledgeFilename("a.md")).toBe(true);
    expect(isAllowedKnowledgeFilename("a.pdf")).toBe(false);
  });

  it("appends welcome/examples/knowledge styles after previous section classes", () => {
    expect(agentCss).toContain(".agent-welcome-editor");
    expect(agentCss).toContain(".agent-example-add");
    expect(agentCss).toContain(".agent-knowledge-upload");
    expect(agentCss.lastIndexOf(".agent-knowledge-upload")).toBeGreaterThan(agentCss.lastIndexOf(".agent-workflow-empty"));
    expect(agentCss.lastIndexOf("/* W26 welcome / examples / knowledge */")).toBeGreaterThan(agentCss.lastIndexOf("/* W27 tools and workflow catalog */"));
    expect(agentCss.lastIndexOf("/* W26 welcome / examples / knowledge */")).toBeGreaterThan(agentCss.lastIndexOf("/* W28 user declarative skills */"));
  });
});

describe("agent config skills section", () => {
  const platformSkill = {
    skill_id: "plat-1",
    owner_scope: "platform",
    source_type: "builtin",
    code: "brief",
    name: "平台简报",
    description: "平台预设",
    instructions: "输出简报",
    risk_level: "low",
    approval_mode: "auto",
    status: "active",
  };
  const userSkill = {
    skill_id: "user-1",
    owner_scope: "user",
    source_type: "custom",
    code: "daily-brief",
    name: "每日简报",
    description: "用户私有",
    instructions: "当用户要简报时汇总",
    risk_level: "medium",
    approval_mode: "once",
    status: "active",
  };
  const pendingImport = {
    import_id: "imp-1",
    source_uri: "https://github.com/example/skill",
    source_ref: "abc123",
    status: "awaiting_confirmation",
    source_metadata: { name: "未确认外部Skill" },
    scan_report: { risk_level: "low", warnings: [], script_types: [] },
  };

  function mountSkills(selected: string[] = ["plat-1"], extra: Record<string, unknown> = {}) {
    return mount(SkillsSection, {
      props: {
        skills: [platformSkill, userSkill],
        selectedSkillIds: selected,
        skillQuery: "",
        candidates: [],
        imports: [pendingImport],
        skillSearching: false,
        importing: false,
        ...extra,
      },
    });
  }

  beforeEach(() => {
    createAgentSkill.mockReset();
    patchAgentSkill.mockReset();
    updateAgentSkills.mockReset();
    createAgentSkill.mockResolvedValue({
      skill_id: "user-2",
      owner_scope: "user",
      source_type: "custom",
      code: "new-skill",
      name: "客服话术",
      description: "新建说明",
      instructions: "按知识库回答",
      risk_level: "low",
      approval_mode: "auto",
      status: "active",
    });
    patchAgentSkill.mockResolvedValue({ config_version_id: "cfg-1", items: [userSkill] });
    updateAgentSkills.mockResolvedValue({ config_version_id: "cfg-1", items: [platformSkill] });
  });

  it("creates a user skill via POST and checks it into the draft binding", async () => {
    const wrapper = mountSkills();
    await wrapper.get(".agent-skill-create-btn").trigger("click");
    expect(wrapper.find("[data-skill-form]").exists()).toBe(true);
    await wrapper.get('[data-skill-field="name"]').setValue("客服话术");
    await wrapper.get('[data-skill-field="description"]').setValue("新建说明");
    await wrapper.get('[data-skill-field="instructions"]').setValue("按知识库回答");
    await wrapper.get('[data-skill-field="risk_level"]').setValue("low");
    await wrapper.get('[data-skill-field="approval_mode"]').setValue("auto");
    await wrapper.get(".agent-skill-save-btn").trigger("click");
    await flushPromises();
    expect(createAgentSkill).toHaveBeenCalledWith("id-1", {
      name: "客服话术",
      description: "新建说明",
      instructions: "按知识库回答",
      risk_level: "low",
      approval_mode: "auto",
    });
    expect(wrapper.text()).toContain("客服话术");
    expect(wrapper.text()).toContain("用户新建");
    const created = wrapper.find('[data-skill-id="user-2"] input');
    expect((created.element as HTMLInputElement).checked).toBe(true);
    expect(wrapper.emitted("update:selectedSkillIds")?.at(-1)?.[0]).toEqual(["plat-1", "user-2"]);
    expect(patchAgentSkill).not.toHaveBeenCalled();
    expect(startSkillImport).not.toHaveBeenCalled();
  });

  it("edits a user skill name, instructions, risk and approval through PATCH", async () => {
    const wrapper = mountSkills(["plat-1", "user-1"]);
    const userRow = wrapper.get('[data-skill-id="user-1"]');
    await userRow.get(".agent-skill-edit-btn").trigger("click");
    await wrapper.get('[data-skill-field="name"]').setValue("晚间简报");
    await wrapper.get('[data-skill-field="instructions"]').setValue("晚上汇总");
    await wrapper.get('[data-skill-field="risk_level"]').setValue("high");
    await wrapper.get('[data-skill-field="approval_mode"]').setValue("always");
    await wrapper.get(".agent-skill-save-btn").trigger("click");
    await flushPromises();
    expect(patchAgentSkill).toHaveBeenCalledWith("id-1", "user-1", {
      name: "晚间简报",
      description: "用户私有",
      instructions: "晚上汇总",
      risk_level: "high",
      approval_mode: "always",
      enabled: true,
    });
    expect(wrapper.text()).toContain("晚间简报");
    expect(wrapper.text()).toContain("高风险");
    expect(wrapper.find('[data-skill-id="plat-1"]').find(".agent-skill-edit-btn").exists()).toBe(false);
  });

  it("binds checked catalog skills to draft and does not treat unconfirmed imports as bound", async () => {
    const wrapper = mountSkills(["plat-1"]);
    expect(wrapper.text()).toContain("未确认外部Skill");
    expect(wrapper.text()).toContain("扫描完成，等待确认");
    expect(wrapper.find('[data-import-status="awaiting_confirmation"]').exists()).toBe(true);
    expect(wrapper.find('[data-skill-id="imp-1"]').exists()).toBe(false);
    const boxes = wrapper.findAll(".agent-skill-list input[type=\"checkbox\"]");
    expect(boxes).toHaveLength(2);
    await wrapper.get('[data-skill-id="user-1"] input').setValue(true);
    await flushPromises();
    expect(updateAgentSkills).toHaveBeenCalledWith("id-1", ["plat-1", "user-1"]);
    expect(createAgentSkill).not.toHaveBeenCalled();
    expect(wrapper.emitted("update:selectedSkillIds")?.at(-1)?.[0]).toEqual(["plat-1", "user-1"]);
  });

  it("keeps skill editor styles appended after earlier section classes", () => {
    const skillSource = readFileSync(resolve(process.cwd(), "src/components/agent-config/sections/SkillsSection.vue"), "utf-8");
    expect(skillSource).toContain("createAgentSkill");
    expect(skillSource).toContain("patchAgentSkill");
    expect(skillSource).toContain("新建 Skill");
    expect(skillSource).toContain("下载并扫描");
    expect(agentCss).toContain(".agent-skill-form");
    expect(agentCss.lastIndexOf(".agent-skill-form")).toBeGreaterThan(agentCss.lastIndexOf(".agent-workflow-empty"));
  });
});


describe("agent config experience memory versions topbar", () => {
  const sections = [
    { id: "prompt", label: "\u63d0\u793a\u8bcd" },
    { id: "experience", label: "\u7ecf\u9a8c" },
    { id: "memory", label: "\u8bb0\u5fc6" },
    { id: "versions", label: "\u7248\u672c" },
  ];

  it("shows plaza back, draft save, publish and draft/published boundary in the topbar", async () => {
    const wrapper = mount(AgentConfigTopbar, {
      props: { status: "draft", savedAt: "", saving: false },
    });
    expect(wrapper.text()).toContain("\u8fd4\u56de\u5e7f\u573a");
    expect(wrapper.text()).toContain("\u4fdd\u5b58\u8349\u7a3f");
    expect(wrapper.text()).toContain("\u53d1\u5e03\u914d\u7f6e");
    expect(wrapper.text()).toContain("\u8349\u7a3f\u7f16\u8f91\u4e2d");
    expect(wrapper.text()).toContain("\u5c1a\u672a\u4fdd\u5b58\u8349\u7a3f");
    expect(wrapper.get("[data-topbar-boundary]").text()).toContain("draft");
    expect(wrapper.get("[data-topbar-boundary]").text()).toContain("published");
    await wrapper.get(".agent-topbar-back").trigger("click");
    await wrapper.findAll("button").find((btn) => btn.text() === "\u4fdd\u5b58\u8349\u7a3f")!.trigger("click");
    await wrapper.findAll("button").find((btn) => btn.text() === "\u53d1\u5e03\u914d\u7f6e")!.trigger("click");
    expect(wrapper.emitted("back")).toBeTruthy();
    expect(wrapper.emitted("save")).toBeTruthy();
    expect(wrapper.emitted("publish")).toBeTruthy();
  });

  it("keeps nav draft/published boundary copy", () => {
    const wrapper = mount(AgentConfigNav, {
      props: { agentTitle: "\u52a9\u624bA", activeSection: "prompt", sections },
    });
    expect(wrapper.text()).toContain("\u8349\u7a3f\u914d\u7f6e");
    expect(wrapper.text()).toContain("\u914d\u7f6e\u8fb9\u754c");
    expect(wrapper.text()).toContain("draft");
    expect(wrapper.text()).toContain("published");
    expect(wrapper.find(".agent-nav-boundary-extra").exists()).toBe(true);
  });

  it("explains opening welcome/examples from existing draft fields without a new column", async () => {
    getAgentConfig.mockResolvedValue({
      config_version_id: "cfg-1",
      welcome_message: "\u4f60\u597d",
      example_questions: ["\u5982\u4f55\u9000\u6b3e", " "],
    });
    const wrapper = mount(ExperienceSection);
    await flushPromises();
    expect(getAgentConfig).toHaveBeenCalledWith("id-1");
    expect(wrapper.text()).toContain("\u5f00\u573a\u4f53\u9a8c");
    expect(wrapper.get("[data-experience-welcome]").text()).toContain("\u5c06\u5c55\u793a");
    expect(wrapper.get("[data-experience-examples]").text()).toContain("1");
    expect(wrapper.text()).toContain("welcome_message");
    expect(wrapper.text()).not.toContain("\u8bc4\u6d4b");
    expect(wrapper.text()).not.toContain("\u8fd0\u8425 Tab");
  });

  it("explains long-term memory is isolated per instance", () => {
    const wrapper = mount(MemorySection);
    expect(wrapper.get("[data-memory-isolation]").text()).toContain("\u5b9e\u4f8b");
    expect(wrapper.text()).toContain("\u8de8\u5b9e\u4f8b");
    expect(wrapper.text()).toContain("published");
    expect(wrapper.text()).toContain("draft");
    expect(wrapper.text()).not.toContain("\u8bc4\u6d4b");
  });

  it("lists config versions and marks published/draft", async () => {
    httpGet.mockResolvedValue({
      data: {
        items: [
          { config_version_id: "cfg-2", version_no: 2, status: "draft", updated_at: "2026-09-29T12:00:00Z" },
          { config_version_id: "cfg-1", version_no: 1, status: "published", updated_at: "2026-09-28T12:00:00Z" },
        ],
      },
    });
    const wrapper = mount(VersionsSection);
    await flushPromises();
    expect(httpGet).toHaveBeenCalledWith("/v1/agent-instances/id-1/config/versions");
    expect(wrapper.get('[data-version-status="published"]').text()).toContain("published");
    expect(wrapper.get('[data-version-status="draft"]').text()).toContain("draft");
    expect(wrapper.get('[data-version-id="cfg-1"]').text()).toContain("v1");
    expect(wrapper.get('[data-version-id="cfg-2"]').text()).toContain("v2");
  });

  it("publishes through the existing topbar publish API", async () => {
    getAgentConfig.mockResolvedValue({
      config_version_id: "cfg-1",
      user_id: "u1",
      agent_instance_id: "id-1",
      version_no: 1,
      status: "draft",
      system_prompt: "\u4f60\u662f\u5ba2\u670d",
      welcome_message: "\u4f60\u597d",
      example_questions: ["\u5982\u4f55\u9000\u6b3e"],
      enabled_tool_codes: ["get_current_datetime"],
      workflow_codes: [],
      knowledge_document_ids: [],
    });
    listPromptTemplates.mockResolvedValue({ items: [] });
    listSkillCatalog.mockResolvedValue({ items: [] });
    listAgentSkills.mockResolvedValue({ config_version_id: "cfg-1", items: [] });
    listAgentKnowledge.mockResolvedValue({ config_version_id: "cfg-1", selected_document_ids: [], items: [] });
    listApprovals.mockResolvedValue({ items: [] });
    getAgentSidebar.mockResolvedValue({ title: "\u52a9\u624bA", intro: "\u5ba2\u670d\u7b80\u4ecb" });
    listAgentInstances.mockResolvedValue({ items: [{ agent_instance_id: "id-1", title: "\u52a9\u624bA", intro: "\u5ba2\u670d\u7b80\u4ecb", template_code: "custom" }] });
    updateAgentConfig.mockResolvedValue({
      config_version_id: "cfg-1",
      user_id: "u1",
      agent_instance_id: "id-1",
      version_no: 1,
      status: "draft",
      system_prompt: "\u4f60\u662f\u5ba2\u670d",
      welcome_message: "\u4f60\u597d",
      example_questions: ["\u5982\u4f55\u9000\u6b3e"],
      enabled_tool_codes: ["get_current_datetime"],
      workflow_codes: [],
      knowledge_document_ids: [],
    });
    updateAgentSkills.mockResolvedValue({ config_version_id: "cfg-1", items: [] });
    publishAgentConfig.mockResolvedValue({
      config_version_id: "cfg-1",
      user_id: "u1",
      agent_instance_id: "id-1",
      version_no: 1,
      status: "published",
      system_prompt: "\u4f60\u662f\u5ba2\u670d",
      welcome_message: "\u4f60\u597d",
      example_questions: ["\u5982\u4f55\u9000\u6b3e"],
      enabled_tool_codes: ["get_current_datetime"],
      workflow_codes: [],
      knowledge_document_ids: [],
    });
    const wrapper = mount(AgentConfigView);
    await flushPromises();
    await wrapper.findAll("button").find((btn) => btn.text() === "\u53d1\u5e03\u914d\u7f6e")!.trigger("click");
    await flushPromises();
    expect(updateAgentConfig).toHaveBeenCalled();
    expect(publishAgentConfig).toHaveBeenCalledWith("id-1");
  });

  it("appends experience/memory/version styles after earlier section classes", () => {
    const experienceSource = readFileSync(resolve(process.cwd(), "src/components/agent-config/sections/ExperienceSection.vue"), "utf-8");
    const memorySource = readFileSync(resolve(process.cwd(), "src/components/agent-config/sections/MemorySection.vue"), "utf-8");
    const versionsSource = readFileSync(resolve(process.cwd(), "src/components/agent-config/sections/VersionsSection.vue"), "utf-8");
    const topbarSource = readFileSync(resolve(process.cwd(), "src/components/agent-config/AgentConfigTopbar.vue"), "utf-8");
    expect(experienceSource).toContain("welcome_message");
    expect(memorySource).toContain("data-memory-isolation");
    expect(versionsSource).toContain("/config/versions");
    expect(topbarSource).toContain("\u8fd4\u56de\u5e7f\u573a");
    expect(agentCss).toContain(".agent-topbar-boundary");
    expect(agentCss).toContain(".agent-version-row");
    expect(agentCss.lastIndexOf(".agent-version-row")).toBeGreaterThan(agentCss.lastIndexOf(".agent-skill-form"));
    expect(experienceSource).not.toContain("\u8bc4\u6d4b");
    expect(memorySource).not.toContain("\u8fd0\u8425 Tab");
  });
});

describe("agent config debug SSE", () => {
  const debugPaneSource = readFileSync(resolve(process.cwd(), "src/components/agent-config/AgentConfigDebugPane.vue"), "utf-8");

  beforeEach(() => {
    getAgentConfig.mockResolvedValue({
      config_version_id: "cfg-1",
      user_id: "u1",
      agent_instance_id: "id-1",
      version_no: 1,
      status: "draft",
      system_prompt: "你是客服",
      welcome_message: "你好",
      example_questions: ["如何退款"],
      enabled_tool_codes: ["get_current_datetime"],
      workflow_codes: [],
      knowledge_document_ids: [],
    });
    listPromptTemplates.mockResolvedValue({ items: [] });
    listSkillCatalog.mockResolvedValue({ items: [] });
    listAgentSkills.mockResolvedValue({ config_version_id: "cfg-1", items: [] });
    listAgentKnowledge.mockResolvedValue({ config_version_id: "cfg-1", selected_document_ids: [], items: [] });
    listApprovals.mockResolvedValue({ items: [] });
    getAgentSidebar.mockResolvedValue({ title: "助手A", intro: "客服简介" });
    listAgentInstances.mockResolvedValue({
      items: [{ agent_instance_id: "id-1", title: "助手A", intro: "客服简介", template_code: "custom" }],
    });
  });

  it("uses debug-open and existing messages SSE instead of draft/preview echo", () => {
    expect(debugPaneSource).toContain("openDebugThread");
    expect(debugPaneSource).toContain("postMessage");
    expect(debugPaneSource).toContain("HitlCard");
    expect(debugPaneSource).toContain("decideApproval");
    expect(debugPaneSource).toContain("resumeThread");
    expect(debugPaneSource).toContain("调试环境，使用未发布草稿");
    expect(debugPaneSource).not.toContain("previewAgentDraft");
    expect(debugPaneSource).not.toContain('emit("preview")');
    expect(debugPaneSource).not.toContain("不会创建正式线程");
    expect(debugPaneSource).not.toContain("不会执行工具");
    expect(debugPaneSource).not.toContain("发送预览");
  });

  it("does not call fake preview when sending a debug message", async () => {
    previewAgentDraft.mockClear();
    postMessage.mockResolvedValue({
      thread_id: "dbg-1",
      thread_kind: "debug",
      messages: [
        { role: "user", content: "hello-debug" },
        { role: "assistant", content: "draft-sse-reply" },
      ],
    });
    const wrapper = mount(AgentConfigView);
    await flushPromises();
    expect(openDebugThread).toHaveBeenCalledWith("id-1");
    expect(getThread).toHaveBeenCalledWith("dbg-1");
    await wrapper.get(".agent-editor-preview textarea").setValue("hello-debug");
    await wrapper.get(".agent-editor-preview .agent-btn").trigger("click");
    await flushPromises();
    expect(postMessage).toHaveBeenCalledWith("dbg-1", "hello-debug", expect.any(String), expect.any(Object));
    expect(previewAgentDraft).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain("draft-sse-reply");
    expect(wrapper.text()).toContain("使用未发布草稿");
  });

  it("renders send_email as a tool approval card instead of skill copy", async () => {
    postMessage.mockResolvedValue({
      thread_id: "dbg-1",
      thread_kind: "debug",
      status: "interrupted",
      interrupt: {
        type: "review_tool",
        approval_kind: "tool",
        approval_id: "appr-email",
        tool: "send_email",
        resource_code: "send_email",
        reason: "发送邮件需要独立工具审批。",
        subject: "hello",
        options: ["approve_once", "approve_session", "deny"],
      },
      messages: [
        { role: "user", content: "发邮件" },
        { role: "assistant", content: "" },
      ],
    });
    const wrapper = mount(AgentConfigView);
    await flushPromises();
    await wrapper.get(".agent-editor-preview textarea").setValue("发邮件");
    await wrapper.get(".agent-editor-preview button.agent-btn").trigger("click");
    await flushPromises();
    const card = wrapper.get('[data-hitl-kind="tool"]');
    expect(card.text()).toContain("工具审批：发送邮件");
    expect(card.text()).toContain("发送邮件需要独立工具审批");
    expect(card.text()).not.toContain("真实发送");
    expect(card.text()).not.toContain("Skill 使用审批");
    expect(wrapper.get(".agent-editor-preview textarea").attributes("disabled")).toBeDefined();
  });

  it("keeps import/skill/script/tool copy independent and resumes after decision", async () => {
    const interrupts = [
      {
        type: "review_import",
        approval_kind: "import",
        approval_id: "appr-import",
        resource_code: "ext-skill",
        reason: "外部 Skill 导入需要独立导入审批。",
      },
      {
        type: "review_skill",
        approval_kind: "skill",
        approval_id: "appr-skill",
        skill_id: "sk-1",
        skill_name: "客服技能",
        reason: "该 Skill 未在当前线程获得独立审批，加载前需要用户确认。",
      },
      {
        type: "review_skill_script",
        approval_kind: "script",
        approval_id: "appr-script",
        skill_id: "sk-1",
        script_path: "main.py",
        reason: "该 Skill 脚本将在受控 Python runner 中执行，需要独立脚本审批。",
      },
      {
        type: "review_tool",
        approval_kind: "tool",
        approval_id: "appr-tool",
        tool: "run_skill_script",
        resource_code: "run_skill_script",
        reason: "该工具需要独立执行审批。",
      },
    ];
    const labels = ["Skill 导入审批", "Skill 使用审批", "Skill 脚本审批", "工具执行审批"];
    const kinds = ["import", "skill", "script", "tool"];
    for (let i = 0; i < interrupts.length; i += 1) {
      decideApproval.mockClear();
      resumeThread.mockClear();
      postMessage.mockResolvedValue({
        thread_id: "dbg-1",
        thread_kind: "debug",
        status: "interrupted",
        interrupt: interrupts[i],
        messages: [{ role: "user", content: `hitl-${kinds[i]}` }],
      });
      resumeThread.mockResolvedValue({
        thread_id: "dbg-1",
        thread_kind: "debug",
        status: "idle",
        interrupt: null,
        messages: [
          { role: "user", content: `hitl-${kinds[i]}` },
          { role: "assistant", content: "resumed-ok" },
        ],
      });
      const wrapper = mount(AgentConfigView);
      await flushPromises();
      await wrapper.get(".agent-editor-preview textarea").setValue(`hitl-${kinds[i]}`);
      await wrapper.get(".agent-editor-preview button.agent-btn").trigger("click");
      await flushPromises();
      const card = wrapper.get(`[data-hitl-kind="${kinds[i]}"]`);
      expect(card.text()).toContain(labels[i]);
      expect(card.text()).not.toContain("真实发送");
      expect(card.text()).not.toContain("生成前需要人工审核");
      const approveBtn = card.findAll("button").find((btn) => btn.text() === "批准");
      expect(approveBtn).toBeTruthy();
      await approveBtn!.trigger("click");
      await flushPromises();
      expect(decideApproval).toHaveBeenCalledWith(interrupts[i].approval_id, true, "用户在调试区批准");
      expect(resumeThread).toHaveBeenCalledWith("dbg-1", { action: "approve_once" });
      expect(wrapper.text()).toContain("resumed-ok");
      wrapper.unmount();
    }
  });

  it("rejects a debug approval through decision and deny resume", async () => {
    postMessage.mockResolvedValue({
      thread_id: "dbg-1",
      thread_kind: "debug",
      status: "interrupted",
      interrupt: {
        type: "review_skill",
        approval_kind: "skill",
        approval_id: "appr-deny",
        skill_name: "客服技能",
        reason: "该 Skill 需要独立使用审批。",
      },
      messages: [{ role: "user", content: "load skill" }],
    });
    resumeThread.mockResolvedValue({
      thread_id: "dbg-1",
      thread_kind: "debug",
      status: "idle",
      interrupt: null,
      messages: [
        { role: "user", content: "load skill" },
        { role: "assistant", content: "denied-ok" },
      ],
    });
    const wrapper = mount(AgentConfigView);
    await flushPromises();
    await wrapper.get(".agent-editor-preview textarea").setValue("load skill");
    await wrapper.get(".agent-editor-preview button.agent-btn").trigger("click");
    await flushPromises();
    const card = wrapper.get('[data-hitl-kind="skill"]');
    expect(card.text()).toContain("Skill 使用审批");
    expect(card.text()).not.toContain("真实发送");
    await card.findAll("button").find((btn) => btn.text() === "拒绝")!.trigger("click");
    await flushPromises();
    expect(decideApproval).toHaveBeenCalledWith("appr-deny", false, "用户在调试区拒绝");
    expect(resumeThread).toHaveBeenCalledWith("dbg-1", { action: "deny" });
  });
});
