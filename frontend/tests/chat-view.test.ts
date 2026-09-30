import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { enableAutoUnmount, mount, flushPromises } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ChatView from "../src/views/ChatView.vue";

enableAutoUnmount(afterEach);

const openAgentInstance = vi.fn();
const getAgentSidebar = vi.fn();
const getThread = vi.fn();
const postMessage = vi.fn();
const resumeThread = vi.fn();
const decideApproval = vi.fn();
const fetchAuthBlob = vi.fn();
const httpGet = vi.fn();
const agentCss = readFileSync(resolve(process.cwd(), "src/styles/agent.css"), "utf-8");

vi.mock("../src/api/agents", () => ({
  openAgentInstance: (...args: unknown[]) => openAgentInstance(...args),
  getAgentSidebar: (...args: unknown[]) => getAgentSidebar(...args),
}));

vi.mock("../src/api/threads", () => ({
  getThread: (...args: unknown[]) => getThread(...args),
  postMessage: (...args: unknown[]) => postMessage(...args),
  resumeThread: (...args: unknown[]) => resumeThread(...args),
  fetchAuthBlob: (...args: unknown[]) => fetchAuthBlob(...args),
}));

vi.mock("../src/api/agentConfig", () => ({
  decideApproval: (...args: unknown[]) => decideApproval(...args),
}));

vi.mock("../src/api/http", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../src/api/http")>();
  return {
    ...actual,
    http: {
      get: (...args: unknown[]) => httpGet(...args),
    },
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

describe("ChatView HITL", () => {
  beforeEach(() => {
    localStorage.setItem("token", "tok");
    setActivePinia(createPinia());
    openAgentInstance.mockResolvedValue({
      agent_instance_id: "id-1",
      thread_id: "thread-1",
      updated_at: "2026-01-01T00:00:00",
    });
    getAgentSidebar.mockResolvedValue({
      title: "助手A",
      capability_description: "规划抖音运营并触达线索",
      development_notes: "能力只展示不勾选",
      agent_mode_label: "单智能体模式",
      knowledge_documents: [{ title: "faq", filename: "faq.md" }],
      workflows: [{ code: "douyin-lead-discovery", display_name: "线索发现与触达" }],
      tools: [{ name: "discover_leads", display_name: "线索发现", user_facing_summary: "扫描并真实发送评论或私信" }],
    });
    fetchAuthBlob.mockRejectedValue(new Error("no avatar"));
    httpGet.mockReset();
    httpGet.mockResolvedValue({ data: { items: [] } });
    getThread.mockReset();
    postMessage.mockReset();
    resumeThread.mockReset();
    decideApproval.mockReset();
    decideApproval.mockResolvedValue({ approval_id: "appr-1", status: "approved" });
  });

  it("disables composer while thread is interrupted", async () => {
    getThread.mockResolvedValue({
      status: "interrupted",
      interrupt: {
        type: "review_media",
        tool: "generate_image",
        prompt: "bottle",
        params: {},
      },
      messages: [],
    });
    const wrapper = mount(ChatView, { global: { plugins: [createPinia()] } });
    await flushPromises();
    expect(wrapper.text()).toContain("Approve");
    expect(wrapper.find(".agent-chat-main > .agent-hitl").exists()).toBe(false);
    expect(wrapper.find(".agent-messages .agent-msg-row.is-hitl .agent-hitl").exists()).toBe(true);
    expect(wrapper.find(".agent-messages .agent-msg-row.is-hitl .agent-msg-avatar").exists()).toBe(true);
    expect(wrapper.find(".agent-bubble-pending").exists()).toBe(false);
    expect(wrapper.get(".agent-composer textarea").attributes("disabled")).toBeDefined();
    expect(wrapper.get(".agent-composer button").attributes("disabled")).toBeDefined();
  });

  it("keeps the pending assistant bubble horizontal and expandable", async () => {
    getThread.mockResolvedValue({ status: "idle", interrupt: null, messages: [] });
    postMessage.mockImplementation(() => new Promise(() => undefined));
    const wrapper = mount(ChatView, { global: { plugins: [createPinia()] } });
    await flushPromises();
    await wrapper.get(".agent-composer textarea").setValue("你好");
    await wrapper.get("form.agent-composer").trigger("submit");
    await flushPromises();

    expect(wrapper.get(".agent-bubble-pending").text()).toContain("正在思考");
    expect(agentCss).toMatch(/\.agent-message-content\s*\{[\s\S]*flex: 0 1 auto;[\s\S]*min-width: 0;/);
    expect(agentCss).toMatch(/\.agent-msg-row \.agent-bubble\s*\{[\s\S]*width: fit-content;[\s\S]*max-width: 100%;/);
    expect(agentCss).toMatch(/\.agent-bubble-pending\s*\{[\s\S]*min-width: 108px;[\s\S]*white-space: nowrap;/);
  });

  it("shows a pending assistant bubble while waiting for a reply", async () => {
    getThread.mockResolvedValue({ status: "idle", interrupt: null, messages: [] });
    let resolvePost: (value: unknown) => void = () => undefined;
    postMessage.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolvePost = resolve;
        }),
    );
    const wrapper = mount(ChatView, { global: { plugins: [createPinia()] } });
    await flushPromises();
    expect(wrapper.find(".agent-bubble-pending").exists()).toBe(false);
    await wrapper.get(".agent-composer textarea").setValue("你好");
    await wrapper.get("form.agent-composer").trigger("submit");
    await flushPromises();
    expect(wrapper.text()).toContain("你好");
    expect(wrapper.get(".agent-bubble-pending").text()).toContain("正在思考");
    const userRow = wrapper.findAll(".agent-msg-row").find((row) => row.classes().includes("is-user"));
    expect(userRow?.find(".agent-msg-avatar").exists()).toBe(false);
    expect(wrapper.find(".agent-msg-row.is-pending .agent-msg-avatar").exists()).toBe(true);
    expect(wrapper.find(".agent-msg-row.is-hitl").exists()).toBe(false);
    resolvePost({
      status: "idle",
      interrupt: null,
      messages: [
        { role: "user", content: "你好" },
        { role: "assistant", content: "您好，我是运营助手" },
      ],
    });
    await flushPromises();
    expect(wrapper.find(".agent-bubble-pending").exists()).toBe(false);
    expect(wrapper.text()).toContain("您好，我是运营助手");
    const assistantRow = wrapper.findAll(".agent-msg-row").find((row) => !row.classes().includes("is-user"));
    expect(assistantRow?.find(".agent-msg-avatar").exists()).toBe(true);
  });

  it("shows agent avatar on assistant rows only", async () => {
    getThread.mockResolvedValue({
      status: "idle",
      interrupt: null,
      messages: [
        { role: "user", content: "你好" },
        { role: "assistant", content: "您好，我是运营助手" },
      ],
    });
    const wrapper = mount(ChatView, { global: { plugins: [createPinia()] } });
    await flushPromises();
    const rows = wrapper.findAll(".agent-messages .agent-msg-row");
    expect(rows).toHaveLength(2);
    expect(rows[0].classes()).toContain("is-user");
    expect(rows[0].find(".agent-msg-avatar").exists()).toBe(false);
    expect(rows[0].text()).toContain("你好");
    expect(rows[1].classes()).not.toContain("is-user");
    expect(rows[1].find(".agent-msg-avatar").exists()).toBe(true);
    expect(rows[1].text()).toContain("您好，我是运营助手");
  });

  it("keeps user and timeout assistant state when chat request times out", async () => {
    getThread.mockResolvedValue({ status: "idle", interrupt: null, messages: [] });
    postMessage.mockRejectedValue(Object.assign(new Error("request timeout"), { code: "ECONNABORTED" }));
    const wrapper = mount(ChatView, { global: { plugins: [createPinia()] } });
    await flushPromises();
    await wrapper.get(".agent-composer textarea").setValue("超时请求");
    await wrapper.get("form.agent-composer").trigger("submit");
    await flushPromises();
    expect(wrapper.find(".agent-msg-row.is-user").text()).toContain("超时请求");
    expect(wrapper.find(".agent-msg-row.is-timeout").text()).toContain("等待超时");
    expect(wrapper.findAll(".agent-msg-row")).toHaveLength(2);
  });

  it("keeps user and error assistant state when chat request fails", async () => {
    getThread.mockResolvedValue({ status: "idle", interrupt: null, messages: [] });
    postMessage.mockRejectedValue(new Error("server failed"));
    const wrapper = mount(ChatView, { global: { plugins: [createPinia()] } });
    await flushPromises();
    await wrapper.get(".agent-composer textarea").setValue("失败请求");
    await wrapper.get("form.agent-composer").trigger("submit");
    await flushPromises();
    expect(wrapper.find(".agent-msg-row.is-user").text()).toContain("失败请求");
    expect(wrapper.find(".agent-msg-row.is-error").text()).toContain("本次回复失败");
    expect(wrapper.text()).toContain("server failed");
  });

  it("keeps identical consecutive user messages as separate requests", async () => {
    getThread.mockResolvedValue({ status: "idle", interrupt: null, messages: [] });
    postMessage.mockImplementation(() => new Promise(() => undefined));
    const wrapper = mount(ChatView, { global: { plugins: [createPinia()] } });
    await flushPromises();
    const composer = wrapper.get(".agent-composer textarea");
    await composer.setValue("重复文本");
    await wrapper.get("form.agent-composer").trigger("submit");
    await composer.setValue("重复文本");
    await wrapper.get("form.agent-composer").trigger("submit");
    await flushPromises();
    expect(wrapper.findAll(".agent-msg-row.is-user")).toHaveLength(2);
    expect(wrapper.findAll(".agent-msg-row.is-pending")).toHaveLength(2);
    expect(postMessage).toHaveBeenCalledTimes(2);
    expect(postMessage.mock.calls[0][2]).not.toBe(postMessage.mock.calls[1][2]);
  });



  it("keeps the main chat column and readonly sidebar together", async () => {
    getThread.mockResolvedValue({ status: "idle", interrupt: null, messages: [] });
    const wrapper = mount(ChatView, { global: { plugins: [createPinia()] } });
    await flushPromises();
    expect(wrapper.find(".agent-chat-main").exists()).toBe(true);
    expect(wrapper.find(".agent-task-rail").exists()).toBe(true);
    expect(wrapper.find(".agent-sidebar").exists()).toBe(true);
    expect(wrapper.find(".agent-chat-column").exists()).toBe(true);
    expect(wrapper.find(".agent-chat-column .agent-messages").exists()).toBe(true);
    expect(wrapper.find(".agent-chat-column form.agent-composer").exists()).toBe(true);
    expect(wrapper.find(".agent-chat-main > form.agent-composer").exists()).toBe(false);
    expect(wrapper.find(".agent-page > form.agent-composer").exists()).toBe(false);
    expect(wrapper.find(".agent-empty").exists()).toBe(true);
    expect(wrapper.find(".agent-sidebar .agent-task-progress").exists()).toBe(false);
    expect(wrapper.find(".agent-task-rail .agent-task-progress").exists()).toBe(true);
    expect(wrapper.get(".agent-task-rail").text()).toContain("当前任务");
    expect(wrapper.get(".agent-task-rail").text()).toContain("暂无进行中的任务");
    expect(wrapper.get(".agent-sidebar").text()).not.toContain("当前任务");
    expect(wrapper.get(".agent-sidebar").text()).not.toContain("暂无进行中的任务");
    expect(agentCss).toMatch(/\.agent-chat-column\s*\{[\s\S]*max-width:\s*860px;/);
    expect(agentCss).toMatch(/\.agent-chat-layout\s*\{[\s\S]*grid-template-columns:\s*400px\s*minmax\(0,\s*1fr\)\s*400px;/);
    expect(agentCss).toMatch(/\.agent-chat-layout\s*\{[\s\S]*grid-template-areas:\s*"task main catalog"/);
    expect(agentCss).toMatch(/\.agent-chat\s*\{[\s\S]*height:\s*100vh;[\s\S]*overflow:\s*hidden;/);
    expect(agentCss).toMatch(/\.agent-task-rail\s*\{[\s\S]*overflow:\s*hidden;/);
    expect(agentCss).toMatch(/\.agent-sidebar\s*\{[\s\S]*overflow:\s*hidden;/);
    expect(agentCss).toMatch(/\.agent-task-progress\s*\{[\s\S]*overflow-y:\s*auto;/);
    expect(agentCss).toMatch(/\.agent-sidebar-catalog\s*\{[\s\S]*overflow-y:\s*auto;/);
    expect(agentCss).toMatch(/@media \(max-width: 900px\)\s*\{[\s\S]*\.agent-chat-layout\s*\{[\s\S]*grid-template-columns:\s*1fr;/);
    expect(agentCss).toMatch(/@media \(max-width: 900px\)\s*\{[\s\S]*\.agent-chat-layout\s*\{[\s\S]*grid-template-areas:\s*"main"\s*"task"\s*"catalog"/);
  });

  it("aligns user messages right and assistant messages left inside the content column", async () => {
    getThread.mockResolvedValue({
      status: "idle",
      interrupt: null,
      messages: [
        { role: "user", content: "你好", created_at: "2026-09-23T12:00:00+08:00" },
        { role: "assistant", content: "您好，我是运营助手", created_at: "2026-09-23T12:00:01+08:00" },
      ],
    });
    const wrapper = mount(ChatView, { global: { plugins: [createPinia()] } });
    await flushPromises();
    const rows = wrapper.findAll(".agent-chat-column .agent-messages .agent-msg-row");
    expect(rows).toHaveLength(2);
    expect(rows[0].classes()).toContain("is-user");
    expect(rows[0].find(".agent-msg-avatar").exists()).toBe(false);
    expect(rows[1].classes()).not.toContain("is-user");
    expect(rows[1].find(".agent-msg-avatar").exists()).toBe(true);
    expect(agentCss).toMatch(/\.agent-msg-row\.is-user\s*\{[\s\S]*justify-content:\s*flex-end;/);
    expect(agentCss).toMatch(/\.agent-msg-row\.is-user \.agent-message-content\s*\{[\s\S]*align-items:\s*flex-end;/);
    expect(agentCss).toMatch(/\.agent-msg-row:not\(\.is-user\) \.agent-message-content\s*\{[\s\S]*align-items:\s*flex-start;/);
    expect(agentCss).toMatch(/\.agent-bubble\s*\{[\s\S]*overflow-wrap:\s*anywhere;[\s\S]*word-break:\s*break-word;/);
    expect(agentCss).toMatch(/\.agent-sidebar\s*\{[\s\S]*overflow-wrap:\s*anywhere;[\s\S]*word-break:\s*break-word;/);
    expect(agentCss).toMatch(/\.agent-bubble-pending\s*\{[\s\S]*min-width:\s*108px;[\s\S]*white-space:\s*nowrap;/);
    expect(agentCss).toMatch(/\.agent-typing-dots\s*\{[\s\S]*display:\s*inline-flex;/);
  });

  it("ignores an older send response after a newer request has started", async () => {
    getThread.mockResolvedValue({ status: "idle", interrupt: null, messages: [] });
    const resolvers: Array<(value: unknown) => void> = [];
    postMessage.mockImplementation(() => new Promise((resolve) => resolvers.push(resolve)));
    const wrapper = mount(ChatView, { global: { plugins: [createPinia()] } });
    await flushPromises();
    const composer = wrapper.get(".agent-composer textarea");
    await composer.setValue("第一条");
    await wrapper.get("form.agent-composer").trigger("submit");
    await composer.setValue("第二条");
    await wrapper.get("form.agent-composer").trigger("submit");
    await flushPromises();
    const firstClientId = postMessage.mock.calls[0][2];
    const secondClientId = postMessage.mock.calls[1][2];
    resolvers[1]({
      status: "idle",
      interrupt: null,
      messages: [
        { role: "user", content: "第二条", message_id: "u2", client_message_id: secondClientId },
        { role: "assistant", content: "第二条回复", message_id: "a2", client_message_id: secondClientId },
      ],
    });
    await flushPromises();
    resolvers[0]({
      status: "idle",
      interrupt: null,
      messages: [
        { role: "user", content: "第一条", message_id: "u1", client_message_id: firstClientId },
        { role: "assistant", content: "第一条回复", message_id: "a1", client_message_id: firstClientId },
      ],
    });
    await flushPromises();
    expect(wrapper.text()).toContain("第二条回复");
    expect(wrapper.text()).not.toContain("第一条回复");
  });

  it("shows local thinking in the sidebar while the main bubble stays pending", async () => {
    getThread.mockResolvedValue({ status: "idle", interrupt: null, messages: [] });
    postMessage.mockImplementation(() => new Promise(() => undefined));
    const wrapper = mount(ChatView, { global: { plugins: [createPinia()] } });
    await flushPromises();
    const pollCallsBeforeSend = getThread.mock.calls.length;
    getThread.mockResolvedValue({
      status: "idle",
      interrupt: null,
      messages: [{ role: "assistant", content: "POLL_WIPE" }],
      progress: { round_id: null, phase: "idle", steps: [] },
    });
    await wrapper.get(".agent-composer textarea").setValue("你好");
    await wrapper.get("form.agent-composer").trigger("submit");
    await flushPromises();
    expect(wrapper.get(".agent-bubble-pending").text()).toContain("正在思考");
    expect(wrapper.get(".agent-task-progress").text()).toContain("正在思考");
    expect(wrapper.get(".agent-task-progress").text()).not.toContain("暂无进行中的任务");
    expect(wrapper.text()).not.toContain("POLL_WIPE");
    expect(getThread.mock.calls.length).toBe(pollCallsBeforeSend);
  });

  it("appends SSE tokens to the pending bubble then applyThread on the final thread", async () => {
    getThread.mockResolvedValue({ status: "idle", interrupt: null, messages: [] });
    let handlers: { onProgress?: Function; onToken?: Function } | undefined;
    let resolvePost: (value: unknown) => void = () => undefined;
    postMessage.mockImplementation(
      (_threadId: string, _content: string, _clientMessageId: string, nextHandlers?: { onProgress?: Function; onToken?: Function }) => {
        handlers = nextHandlers;
        return new Promise((resolve) => {
          resolvePost = resolve;
        });
      },
    );
    const wrapper = mount(ChatView, { global: { plugins: [createPinia()] } });
    await flushPromises();
    await wrapper.get(".agent-composer textarea").setValue("你好");
    await wrapper.get("form.agent-composer").trigger("submit");
    await flushPromises();
    expect(wrapper.get(".agent-bubble-pending").text()).toContain("正在思考");
    handlers?.onToken?.("你好");
    await flushPromises();
    expect(wrapper.get(".agent-bubble-pending").text()).toContain("你好");
    expect(wrapper.get(".agent-bubble-pending").text()).not.toContain("正在回复");
    const clientMessageId = String(postMessage.mock.calls[0][2]);
    resolvePost({
      status: "idle",
      interrupt: null,
      messages: [
        { role: "user", content: "你好", message_id: "u1", client_message_id: clientMessageId },
        { role: "assistant", content: "你好世界", message_id: "a1", client_message_id: clientMessageId },
      ],
    });
    await flushPromises();
    expect(wrapper.find(".agent-bubble-pending").exists()).toBe(false);
    expect(wrapper.text()).toContain("你好世界");
  });

  it("drops early tokens when progress phase becomes running", async () => {
    getThread.mockResolvedValue({ status: "idle", interrupt: null, messages: [] });
    let handlers: { onProgress?: Function; onToken?: Function } | undefined;
    postMessage.mockImplementation(
      (_threadId: string, _content: string, _clientMessageId: string, nextHandlers?: { onProgress?: Function; onToken?: Function }) => {
        handlers = nextHandlers;
        return new Promise(() => undefined);
      },
    );
    const wrapper = mount(ChatView, { global: { plugins: [createPinia()] } });
    await flushPromises();
    await wrapper.get(".agent-composer textarea").setValue("找线索");
    await wrapper.get("form.agent-composer").trigger("submit");
    await flushPromises();
    handlers?.onToken?.("提前草稿");
    await flushPromises();
    expect(wrapper.get(".agent-bubble-pending").text()).toContain("提前草稿");
    const clientMessageId = String(postMessage.mock.calls[0][2]);
    handlers?.onProgress?.({
      round_id: clientMessageId,
      phase: "running",
      steps: [
        { id: "thinking", kind: "thinking", tool: null, label: "正在思考", status: "done", spin: false },
        {
          id: "tool:discover_leads:c1",
          kind: "tool",
          tool: "discover_leads",
          label: "正在运行「线索发现与触达」",
          status: "running",
          spin: true,
          children: [
            { id: "dify:n1:0", kind: "dify_node", tool: "discover_leads", label: "开始", status: "done", spin: false },
            { id: "dify:n2:1", kind: "dify_node", tool: "discover_leads", label: "请求抖音", status: "running", spin: true },
            { id: "dify:n3:2", kind: "dify_node", tool: "discover_leads", label: "失败节点", status: "failed", spin: false },
          ],
        },
      ],
    });
    await flushPromises();
    expect(wrapper.get(".agent-bubble-pending").text()).toContain("请求抖音");
    expect(wrapper.get(".agent-bubble-pending").text()).not.toContain("正在回复");
    expect(wrapper.get(".agent-bubble-pending").text()).not.toContain("提前草稿");
    expect(wrapper.get(".agent-task-progress").text()).toContain("正在运行「线索发现与触达」");
    expect(wrapper.get(".agent-task-progress").text()).toContain("开始");
    expect(wrapper.get(".agent-task-progress").text()).toContain("请求抖音");
    expect(wrapper.get(".agent-task-progress").text()).toContain("失败节点");
    expect(wrapper.get(".agent-task-fail").text()).toBe("✕");
    handlers?.onToken?.("找到线索");
    await flushPromises();
    expect(wrapper.get(".agent-bubble-pending").text()).toContain("找到线索");
    expect(wrapper.get(".agent-bubble-pending").text()).not.toContain("请求抖音");
  });

  it("keeps task history after the final reply and resets only on the next user message", async () => {
    getThread.mockResolvedValue({ status: "idle", interrupt: null, messages: [] });
    postMessage.mockImplementation(async (_threadId: string, content: string, clientMessageId: string) => ({
      status: "idle",
      interrupt: null,
      messages: [
        { role: "user", content, message_id: "u1", client_message_id: clientMessageId },
        { role: "assistant", content: "检索完成", message_id: "a1", client_message_id: clientMessageId },
      ],
      progress: {
        round_id: clientMessageId,
        phase: "done",
        steps: [
          { id: "thinking", kind: "thinking", tool: null, label: "正在思考", status: "done", spin: false },
          { id: "tool:search_kb:c1", kind: "tool", tool: "search_kb", label: "知识库检索", status: "done", spin: false },
          { id: "composing", kind: "composing", tool: null, label: "正在整理回复", status: "done", spin: false },
        ],
      },
    }));
    const wrapper = mount(ChatView, { global: { plugins: [createPinia()] } });
    await flushPromises();
    await wrapper.get(".agent-composer textarea").setValue("搜知识库");
    await wrapper.get("form.agent-composer").trigger("submit");
    await flushPromises();
    expect(wrapper.find(".agent-bubble-pending").exists()).toBe(false);
    expect(wrapper.text()).toContain("检索完成");
    expect(wrapper.get(".agent-task-progress").text()).toContain("知识库检索");
    expect(wrapper.get(".agent-task-progress").text()).toContain("正在整理回复");
    postMessage.mockImplementation(() => new Promise(() => undefined));
    await wrapper.get(".agent-composer textarea").setValue("下一问");
    await wrapper.get("form.agent-composer").trigger("submit");
    await flushPromises();
    expect(wrapper.get(".agent-bubble-pending").text()).toContain("正在思考");
    expect(wrapper.get(".agent-task-progress").text()).toContain("正在思考");
    expect(wrapper.get(".agent-task-progress").text()).not.toContain("知识库检索");
    expect(wrapper.get(".agent-task-progress").text()).not.toContain("正在整理回复");
  });

  it("does not reset the task panel after Approve", async () => {
    getThread.mockResolvedValue({
      status: "interrupted",
      interrupt: {
        type: "review_media",
        tool: "generate_image",
        prompt: "bottle",
        params: {},
      },
      messages: [{ role: "user", content: "生图", client_message_id: "client-1" }],
      progress: {
        round_id: "client-1",
        phase: "waiting_review",
        steps: [
          { id: "thinking", kind: "thinking", tool: null, label: "正在思考", status: "done", spin: false },
          { id: "tool:generate_image:c1", kind: "review", tool: "generate_image", label: "等待审核「生成图片」", status: "waiting", spin: false },
        ],
      },
    });
    resumeThread.mockImplementation(() => new Promise(() => undefined));
    const wrapper = mount(ChatView, { global: { plugins: [createPinia()] } });
    await flushPromises();
    expect(wrapper.get(".agent-task-progress").text()).toContain("等待审核「生成图片」");
    expect(wrapper.get(".agent-composer textarea").attributes("disabled")).toBeDefined();
    await wrapper.get(".agent-hitl button.agent-btn").trigger("click");
    await flushPromises();
    expect(decideApproval).not.toHaveBeenCalled();
    expect(resumeThread).toHaveBeenCalledWith(
      "thread-1",
      { action: "approve", prompt: "bottle", params: {} },
      expect.any(Object),
    );
    expect(wrapper.get(".agent-task-progress").text()).toContain("等待审核「生成图片」");
    expect(wrapper.get(".agent-task-progress").text()).not.toContain("暂无进行中的任务");
    expect(wrapper.findAll(".agent-task-steps li")).toHaveLength(2);
  });

  it("marks Skip as done immediately and ignores later composing progress", async () => {
    getThread.mockResolvedValue({
      status: "interrupted",
      interrupt: {
        type: "review_media",
        tool: "generate_image",
        prompt: "bottle",
        params: {},
      },
      messages: [{ role: "user", content: "生图", client_message_id: "client-1" }],
      progress: {
        round_id: "client-1",
        phase: "waiting_review",
        steps: [
          { id: "thinking", kind: "thinking", tool: null, label: "正在思考", status: "done", spin: false },
          { id: "tool:generate_image:c1", kind: "review", tool: "generate_image", label: "等待审核「生成图片」", status: "waiting", spin: false },
        ],
      },
    });
    let resolveResume: (value: unknown) => void = () => undefined;
    resumeThread.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveResume = resolve;
        }),
    );
    const wrapper = mount(ChatView, { global: { plugins: [createPinia()] } });
    await flushPromises();
    await wrapper.get(".agent-hitl button.agent-btn-ghost").trigger("click");
    await flushPromises();
    expect(wrapper.get(".agent-task-progress").text()).toContain("已跳过「生成图片」");
    expect(wrapper.get(".agent-task-progress").text()).not.toContain("正在整理回复");
    expect(wrapper.get(".agent-task-progress").text()).not.toContain("等待审核「生成图片」");
    resolveResume({
      status: "idle",
      interrupt: null,
      messages: [
        { role: "user", content: "生图", client_message_id: "client-1" },
        { role: "assistant", content: "已跳过生图", client_message_id: "client-1" },
      ],
      progress: {
        round_id: "client-1",
        phase: "composing",
        steps: [
          { id: "thinking", kind: "thinking", tool: null, label: "正在思考", status: "done", spin: false },
          { id: "tool:generate_image:c1", kind: "tool", tool: "generate_image", label: "正在生成图片", status: "done", spin: false },
          { id: "composing", kind: "composing", tool: null, label: "正在整理回复", status: "running", spin: true },
        ],
      },
    });
    await flushPromises();
    expect(wrapper.get(".agent-task-progress").text()).toContain("已跳过「生成图片」");
    expect(wrapper.get(".agent-task-progress").text()).not.toContain("正在整理回复");
    expect(wrapper.text()).toContain("已跳过生图");
  });

  it("keeps image HITL copy and Dify send hint while rendering four approval kinds", async () => {
    const interrupts = [
      {
        type: "review_import",
        approval_kind: "import",
        approval_id: "appr-import",
        resource_code: "ext-skill",
        reason: "外部 Skill 导入需要独立导入审批。",
        heading: "Skill 导入审批",
        kind: "import",
      },
      {
        type: "review_skill",
        approval_kind: "skill",
        approval_id: "appr-skill",
        skill_name: "客服技能",
        reason: "该 Skill 需要独立使用审批。",
        heading: "Skill 使用审批",
        kind: "skill",
      },
      {
        type: "review_skill_script",
        approval_kind: "script",
        approval_id: "appr-script",
        script_path: "main.py",
        reason: "该 Skill 脚本需要独立脚本审批。",
        heading: "Skill 脚本审批",
        kind: "script",
      },
      {
        type: "review_tool",
        approval_kind: "tool",
        approval_id: "appr-tool",
        tool: "run_skill_script",
        resource_code: "run_skill_script",
        reason: "该工具需要独立执行审批。",
        heading: "工具执行审批",
        kind: "tool",
      },
    ];
    for (const item of interrupts) {
      decideApproval.mockClear();
      resumeThread.mockReset();
      resumeThread.mockResolvedValue({
        status: "idle",
        interrupt: null,
        messages: [
          { role: "user", content: `hitl-${item.kind}` },
          { role: "assistant", content: "resumed-ok" },
        ],
      });
      getThread.mockResolvedValue({
        status: "interrupted",
        interrupt: item,
        messages: [{ role: "user", content: `hitl-${item.kind}` }],
      });
      const wrapper = mount(ChatView, { global: { plugins: [createPinia()] } });
      await flushPromises();
      expect(wrapper.get(".agent-sidebar").text()).toContain("扫描并真实发送评论或私信");
      const card = wrapper.get(`[data-hitl-kind="${item.kind}"]`);
      expect(card.text()).toContain(item.heading);
      expect(card.text()).not.toContain("真实发送");
      expect(card.text()).not.toContain("生成前需要人工审核");
      expect(card.text()).not.toContain("Approve");
      expect(wrapper.get(".agent-composer textarea").attributes("disabled")).toBeDefined();
      const approveBtn = card.findAll("button").find((btn) => btn.text() === "批准");
      expect(approveBtn).toBeTruthy();
      await approveBtn!.trigger("click");
      await flushPromises();
      expect(decideApproval).toHaveBeenCalledWith(item.approval_id, true, "用户在正式聊天批准");
      expect(resumeThread).toHaveBeenCalledWith("thread-1", { action: "approve_once" }, expect.any(Object));
      expect(wrapper.text()).toContain("resumed-ok");
      wrapper.unmount();
    }
  });

  it("shows send_email as a tool approval instead of skill or Dify send copy", async () => {
    getThread.mockResolvedValue({
      status: "interrupted",
      interrupt: {
        type: "review_tool",
        approval_kind: "tool",
        approval_id: "appr-email",
        tool: "send_email",
        resource_code: "send_email",
        reason: "发送邮件需要独立工具审批。",
        subject: "hello",
      },
      messages: [{ role: "user", content: "发邮件" }],
    });
    const wrapper = mount(ChatView, { global: { plugins: [createPinia()] } });
    await flushPromises();
    const card = wrapper.get('[data-hitl-kind="tool"]');
    expect(card.text()).toContain("工具审批：发送邮件");
    expect(card.text()).toContain("发送邮件需要独立工具审批");
    expect(card.text()).not.toContain("真实发送");
    expect(card.text()).not.toContain("Skill 使用审批");
    expect(wrapper.get(".agent-sidebar").text()).toContain("扫描并真实发送评论或私信");
    expect(wrapper.get(".agent-composer textarea").attributes("disabled")).toBeDefined();
  });

  it("rejects an official skill approval through decision and deny resume", async () => {
    getThread.mockResolvedValue({
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
      status: "idle",
      interrupt: null,
      messages: [
        { role: "user", content: "load skill" },
        { role: "assistant", content: "denied-ok" },
      ],
    });
    const wrapper = mount(ChatView, { global: { plugins: [createPinia()] } });
    await flushPromises();
    const card = wrapper.get('[data-hitl-kind="skill"]');
    expect(card.text()).toContain("Skill 使用审批");
    expect(card.text()).not.toContain("真实发送");
    expect(wrapper.get(".agent-sidebar").text()).toContain("扫描并真实发送评论或私信");
    await card.findAll("button").find((btn) => btn.text() === "拒绝")!.trigger("click");
    await flushPromises();
    expect(decideApproval).toHaveBeenCalledWith("appr-deny", false, "用户在正式聊天拒绝");
    expect(resumeThread).toHaveBeenCalledWith("thread-1", { action: "deny" }, expect.any(Object));
    expect(wrapper.text()).toContain("denied-ok");
  });

  it("keeps video media HITL as Approve/Skip without four-kind copy", async () => {
    getThread.mockResolvedValue({
      status: "interrupted",
      interrupt: {
        type: "review_media",
        tool: "generate_video",
        prompt: "clip",
        params: { duration: 4 },
      },
      messages: [{ role: "user", content: "生视频" }],
    });
    const wrapper = mount(ChatView, { global: { plugins: [createPinia()] } });
    await flushPromises();
    const card = wrapper.get('[data-hitl-kind="media"]');
    expect(card.text()).toContain("Approve");
    expect(card.text()).toContain("Skip");
    expect(card.text()).toContain("生成前需要人工审核");
    expect(card.text()).not.toContain("Skill 使用审批");
    expect(card.text()).not.toContain("批准");
    expect(wrapper.get(".agent-sidebar").text()).toContain("扫描并真实发送评论或私信");
  });


  it("shows published welcome and sends a clicked example question", async () => {
    getThread.mockResolvedValue({ status: "idle", interrupt: null, messages: [], thread_kind: "official" });
    httpGet.mockResolvedValue({
      data: {
        items: [
          {
            status: "draft",
            version_no: 2,
            welcome_message: "draft-welcome",
            example_questions: ["draft-q"],
          },
          {
            status: "published",
            version_no: 1,
            welcome_message: "published-welcome",
            example_questions: ["published-q"],
          },
        ],
      },
    });
    postMessage.mockImplementation(() => new Promise(() => undefined));
    const wrapper = mount(ChatView, { global: { plugins: [createPinia()] } });
    await flushPromises();
    expect(httpGet).toHaveBeenCalledWith("/v1/agent-instances/id-1/config/versions");
    expect(wrapper.get(".agent-empty").text()).toContain("published-welcome");
    expect(wrapper.get(".agent-empty").text()).not.toContain("draft-welcome");
    expect(wrapper.get("[data-example-question]").text()).toBe("published-q");
    await wrapper.get("[data-example-question]").trigger("click");
    await flushPromises();
    expect(postMessage).toHaveBeenCalledWith("thread-1", "published-q", expect.any(String), expect.any(Object));
    expect(wrapper.find(".agent-empty").exists()).toBe(false);
  });

  it("keeps the old empty hint when published welcome is missing", async () => {
    getThread.mockResolvedValue({ status: "idle", interrupt: null, messages: [] });
    httpGet.mockResolvedValue({
      data: {
        items: [{ status: "draft", welcome_message: "draft-welcome", example_questions: ["draft-q"] }],
      },
    });
    const wrapper = mount(ChatView, { global: { plugins: [createPinia()] } });
    await flushPromises();
    expect(wrapper.get(".agent-empty").text()).toBe("\u53d1\u9001\u4e00\u6761\u6d88\u606f\u5f00\u59cb\u5bf9\u8bdd");
    expect(wrapper.text()).not.toContain("draft-welcome");
    expect(wrapper.find("[data-example-question]").exists()).toBe(false);
  });

  it("does not show published welcome on a debug thread", async () => {
    getThread.mockResolvedValue({ status: "idle", interrupt: null, messages: [], thread_kind: "debug" });
    httpGet.mockResolvedValue({
      data: { items: [{ status: "published", welcome_message: "published-welcome", example_questions: ["published-q"] }] },
    });
    const wrapper = mount(ChatView, { global: { plugins: [createPinia()] } });
    await flushPromises();
    expect(wrapper.get(".agent-empty").text()).toBe("\u53d1\u9001\u4e00\u6761\u6d88\u606f\u5f00\u59cb\u5bf9\u8bdd");
    expect(wrapper.text()).not.toContain("published-welcome");
    expect(wrapper.find("[data-example-question]").exists()).toBe(false);
  });

});
