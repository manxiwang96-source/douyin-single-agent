import { mount, flushPromises } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import axios from "axios";
import { createMemoryHistory, createRouter } from "vue-router";
import AgentCard from "../src/components/AgentCard.vue";
import ChatSidebar from "../src/components/ChatSidebar.vue";
import CreateAgentModal from "../src/components/CreateAgentModal.vue";
import HitlCard from "../src/components/HitlCard.vue";
import PlazaView from "../src/views/PlazaView.vue";
import { sidebarView } from "../src/lib/chat";
import type { AgentCard as Card } from "../src/lib/plaza";

vi.mock("../src/api/agents", () => ({
  createAgentInstance: vi.fn(),
  patchAgentInstance: vi.fn(),
  archiveAgentInstance: vi.fn(),
  listAgentInstances: vi.fn(),
  openAgentInstance: vi.fn(),
  getAgentSidebar: vi.fn(),
}));

vi.mock("../src/api/threads", () => ({
  fetchAuthBlob: vi.fn().mockRejectedValue(new Error("no avatar")),
}));

vi.mock("../src/lib/avatar", () => ({
  fileToDataUrl: vi.fn(async () => "data:image/png;base64,xx"),
}));

import {
  archiveAgentInstance,
  createAgentInstance,
  listAgentInstances,
  openAgentInstance,
  patchAgentInstance,
} from "../src/api/agents";
import { fileToDataUrl } from "../src/lib/avatar";

const sampleCard: Card = {
  agent_instance_id: "id-1",
  title: "助手A",
  intro: "日常运营",
  avatar_url: "/v1/agent-instances/id-1/avatar",
  agent_mode: "single",
  agent_mode_label: "单智能体模式",
  created_at: "2026-01-01T00:00:00",
  updated_at: "2026-01-02T00:00:00",
};

function axiosError(detail: string, status: number) {
  const error = {
    isAxiosError: true,
    response: { data: { detail }, status },
    toJSON: () => ({}),
    name: "AxiosError",
    message: String(status),
  };
  Object.setPrototypeOf(error, axios.AxiosError.prototype);
  return error;
}

async function mountPlaza() {
  const pinia = createPinia();
  setActivePinia(pinia);
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/login", name: "login", component: { template: "<div>login</div>" } },
      { path: "/agents", name: "plaza", component: PlazaView },
      {
        path: "/agents/:agentInstanceId",
        name: "chat",
        component: { template: "<div>chat</div>" },
      },
    ],
  });
  await router.push("/agents");
  await router.isReady();
  const wrapper = mount(PlazaView, {
    global: { plugins: [pinia, router] },
  });
  await flushPromises();
  return wrapper;
}

describe("vue components", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(listAgentInstances).mockResolvedValue({
      items: [
        {
          agent_instance_id: "id-1",
          title: "助手A",
          intro: "日常运营",
          avatar_url: "/v1/agent-instances/id-1/avatar",
          agent_mode: "single",
          created_at: "2026-01-01T00:00:00",
          updated_at: "2026-01-02T00:00:00",
        },
      ],
    });
    vi.mocked(createAgentInstance).mockResolvedValue({ agent_instance_id: "id-1" });
    vi.mocked(patchAgentInstance).mockResolvedValue({ agent_instance_id: "id-1" });
    vi.mocked(archiveAgentInstance).mockResolvedValue({
      ok: true,
      agent_instance_id: "id-1",
      status: "archived",
    });
    vi.mocked(openAgentInstance).mockResolvedValue({
      agent_instance_id: "id-1",
      thread_id: "thread-1",
      updated_at: "2026-01-02T00:00:00",
    });
    vi.mocked(fileToDataUrl).mockResolvedValue("data:image/png;base64,xx");
  });

  it("create modal stays on two steps without changing route", async () => {
    const wrapper = mount(CreateAgentModal, { props: { open: true } });
    expect(wrapper.text()).toContain("抖音运营助手");
    expect(wrapper.text()).not.toContain("对话式智能体");
    await wrapper.get(".agent-template").trigger("click");
    expect(wrapper.text()).toContain("名称*");
    expect(wrapper.text()).toContain("简介*");
    expect(wrapper.text()).toContain("本机上传头像");
    expect(wrapper.text()).not.toContain("AI生成头像");
    await wrapper.get("input").setValue("助手A");
    await wrapper.get("textarea").setValue("日常运营");
    await wrapper.get("form").trigger("submit");
    await flushPromises();
    expect(createAgentInstance).toHaveBeenCalledWith("助手A", "日常运营", null);
  });

  it("edit mode opens on profile step and patches without avatar", async () => {
    const wrapper = mount(CreateAgentModal, { props: { open: true, card: sampleCard } });
    expect(wrapper.text()).toContain("编辑智能体");
    expect(wrapper.text()).toContain("保存");
    expect(wrapper.find(".agent-template").exists()).toBe(false);
    expect(wrapper.text()).not.toContain("抖音运营助手");
    await wrapper.get("form").trigger("submit");
    await flushPromises();
    expect(patchAgentInstance).toHaveBeenCalledWith("id-1", { title: "助手A", intro: "日常运营" });
    expect(Object.keys(vi.mocked(patchAgentInstance).mock.calls[0][1]).sort()).toEqual(["intro", "title"]);
    expect(createAgentInstance).not.toHaveBeenCalled();
  });

  it("edit mode includes avatar only after a new image is chosen", async () => {
    const wrapper = mount(CreateAgentModal, { props: { open: true, card: sampleCard } });
    const input = wrapper.get('input[type="file"]');
    Object.defineProperty(input.element, "files", {
      value: [new File(["x"], "a.png", { type: "image/png" })],
    });
    await input.trigger("change");
    await flushPromises();
    await wrapper.get("form").trigger("submit");
    await flushPromises();
    expect(patchAgentInstance).toHaveBeenCalledWith("id-1", {
      title: "助手A",
      intro: "日常运营",
      avatar: "data:image/png;base64,xx",
    });
  });

  it("shows name-in-use copy when patch returns 409", async () => {
    vi.mocked(patchAgentInstance).mockRejectedValue(axiosError("title already in use", 409));
    const wrapper = mount(CreateAgentModal, { props: { open: true, card: sampleCard } });
    await wrapper.get("form").trigger("submit");
    await flushPromises();
    expect(wrapper.text()).toContain("名称已被使用");
  });

  it("card footer buttons do not emit open click", async () => {
    const wrapper = mount(AgentCard, { props: { card: sampleCard } });
    await wrapper.get(".agent-card-edit").trigger("click");
    await wrapper.get(".agent-card-archive").trigger("click");
    expect(wrapper.emitted("edit")?.[0]).toEqual(["id-1"]);
    expect(wrapper.emitted("archive")?.[0]).toEqual(["id-1"]);
    expect(wrapper.emitted("click")).toBeFalsy();
    await wrapper.get(".agent-card-main").trigger("click");
    expect(wrapper.emitted("click")?.[0]).toEqual(["id-1"]);
  });

  it("archive confirm calls delete and cancel does not", async () => {
    const wrapper = await mountPlaza();
    expect(wrapper.text()).toContain("编辑");
    expect(wrapper.text()).toContain("归档");
    await wrapper.get(".agent-card-archive").trigger("click");
    expect(wrapper.text()).toContain("不是物理删除");
    expect(archiveAgentInstance).not.toHaveBeenCalled();
    expect(openAgentInstance).not.toHaveBeenCalled();
    await wrapper.get(".agent-archive-cancel").trigger("click");
    expect(archiveAgentInstance).not.toHaveBeenCalled();
    expect(wrapper.find(".agent-archive-mask").exists()).toBe(false);
    await wrapper.get(".agent-card-archive").trigger("click");
    await wrapper.get(".agent-archive-confirm").trigger("click");
    await flushPromises();
    expect(archiveAgentInstance).toHaveBeenCalledWith("id-1");
    expect(openAgentInstance).not.toHaveBeenCalled();
    expect(listAgentInstances).toHaveBeenCalledTimes(2);
  });

  it("sidebar renders catalog fields and no model", () => {
    const wrapper = mount(ChatSidebar, {
      props: {
        sidebar: sidebarView({
          capability_description: "规划抖音运营并触达线索",
          development_notes: "能力只展示不勾选",
          agent_mode_label: "单智能体模式",
          knowledge_documents: [{ title: "faq", filename: "faq.md" }],
          workflows: [{ code: "douyin-lead-discovery", display_name: "抖音线索发现与触达" }],
          tools: [{ name: "discover_douyin_leads", display_name: "抖音线索发现", user_facing_summary: "真实发送" }],
          model: "hidden",
        }),
      },
    });
    expect(wrapper.text()).toContain("规划抖音运营并触达线索");
    expect(wrapper.text()).toContain("能力只展示不勾选");
    expect(wrapper.text()).toContain("faq");
    expect(wrapper.text()).toContain("抖音线索发现与触达");
    expect(wrapper.text()).toContain("抖音线索发现");
    expect(wrapper.text()).toContain("多智能体模式");
    expect(wrapper.text()).not.toContain("hidden");
    expect(wrapper.html()).not.toContain("model");
  });

  it("HITL card exposes approve/skip and chat helpers disable input", async () => {
    const wrapper = mount(HitlCard, {
      props: {
        visible: true,
        tool: "generate_image",
        prompt: "bottle",
        params: { quality: "low" },
      },
    });
    await wrapper.get("button.agent-btn").trigger("click");
    expect(wrapper.emitted("approve")?.[0][0]).toEqual({
      prompt: "bottle",
      params: { quality: "low" },
    });
    await wrapper.get("button.agent-btn-ghost").trigger("click");
    expect(wrapper.emitted("skip")).toBeTruthy();
  });
});
