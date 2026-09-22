import { mount, flushPromises } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ChatView from "../src/views/ChatView.vue";

const openAgentInstance = vi.fn();
const getAgentSidebar = vi.fn();
const getThread = vi.fn();
const fetchAuthBlob = vi.fn();

vi.mock("../src/api/agents", () => ({
  openAgentInstance: (...args: unknown[]) => openAgentInstance(...args),
  getAgentSidebar: (...args: unknown[]) => getAgentSidebar(...args),
}));

vi.mock("../src/api/threads", () => ({
  getThread: (...args: unknown[]) => getThread(...args),
  postMessage: vi.fn(),
  resumeThread: vi.fn(),
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
    expect(wrapper.get(".agent-composer textarea").attributes("disabled")).toBeDefined();
    expect(wrapper.get(".agent-composer button").attributes("disabled")).toBeDefined();
  });
});
