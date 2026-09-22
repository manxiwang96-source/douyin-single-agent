import { mount, flushPromises } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ChatView from "../src/views/ChatView.vue";

const openAgentInstance = vi.fn();
const getAgentSidebar = vi.fn();
const getThread = vi.fn();
const postMessage = vi.fn();
const resumeThread = vi.fn();
const fetchAuthBlob = vi.fn();

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
      workflows: [{ code: "douyin-lead-discovery", display_name: "抖音线索发现与触达" }],
      tools: [{ name: "discover_douyin_leads", display_name: "抖音线索发现" }],
    });
    fetchAuthBlob.mockRejectedValue(new Error("no avatar"));
    postMessage.mockReset();
    resumeThread.mockReset();
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
    expect(wrapper.get(".agent-bubble-pending").text()).toContain("正在回复");
    const userRow = wrapper.findAll(".agent-msg-row").find((row) => row.classes().includes("is-user"));
    expect(userRow?.find(".agent-msg-avatar").exists()).toBe(false);
    expect(wrapper.find(".agent-msg-row.is-pending .agent-msg-avatar").exists()).toBe(true);
    expect(wrapper.find(".agent-msg-row.is-hitl").exists()).toBe(false);
    resolvePost({
      status: "idle",
      interrupt: null,
      messages: [
        { role: "user", content: "你好" },
        { role: "assistant", content: "您好，我是抖音运营助手" },
      ],
    });
    await flushPromises();
    expect(wrapper.find(".agent-bubble-pending").exists()).toBe(false);
    expect(wrapper.text()).toContain("您好，我是抖音运营助手");
    const assistantRow = wrapper.findAll(".agent-msg-row").find((row) => !row.classes().includes("is-user"));
    expect(assistantRow?.find(".agent-msg-avatar").exists()).toBe(true);
  });

  it("shows agent avatar on assistant rows only", async () => {
    getThread.mockResolvedValue({
      status: "idle",
      interrupt: null,
      messages: [
        { role: "user", content: "你好" },
        { role: "assistant", content: "您好，我是抖音运营助手" },
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
    expect(rows[1].text()).toContain("您好，我是抖音运营助手");
  });
});
