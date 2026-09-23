import { mount, flushPromises } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { defineComponent } from "vue";
import { createMemoryHistory, createRouter, RouterView } from "vue-router";
import LoginView from "../src/views/LoginView.vue";
import PlazaView from "../src/views/PlazaView.vue";
import ChatView from "../src/views/ChatView.vue";

const login = vi.fn();
const register = vi.fn();
const logout = vi.fn();
const listAgentInstances = vi.fn();
const createAgentInstance = vi.fn();
const patchAgentInstance = vi.fn();
const archiveAgentInstance = vi.fn();
const openAgentInstance = vi.fn();
const getAgentSidebar = vi.fn();
const getThread = vi.fn();
const postMessage = vi.fn();
const fetchAuthBlob = vi.fn();

vi.mock("../src/api/auth", () => ({
  login: (...args: unknown[]) => login(...args),
  register: (...args: unknown[]) => register(...args),
  logout: (...args: unknown[]) => logout(...args),
  me: vi.fn(),
}));

vi.mock("../src/api/agents", () => ({
  listAgentInstances: (...args: unknown[]) => listAgentInstances(...args),
  createAgentInstance: (...args: unknown[]) => createAgentInstance(...args),
  patchAgentInstance: (...args: unknown[]) => patchAgentInstance(...args),
  archiveAgentInstance: (...args: unknown[]) => archiveAgentInstance(...args),
  openAgentInstance: (...args: unknown[]) => openAgentInstance(...args),
  getAgentSidebar: (...args: unknown[]) => getAgentSidebar(...args),
}));

vi.mock("../src/api/threads", () => ({
  getThread: (...args: unknown[]) => getThread(...args),
  postMessage: (...args: unknown[]) => postMessage(...args),
  resumeThread: vi.fn(),
  fetchAuthBlob: (...args: unknown[]) => fetchAuthBlob(...args),
}));

const Root = defineComponent({
  name: "Root",
  components: { RouterView },
  template: "<RouterView />",
});

async function mountApp() {
  const pinia = createPinia();
  setActivePinia(pinia);
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/login", name: "login", component: LoginView, meta: { public: true } },
      { path: "/agents", name: "plaza", component: PlazaView, meta: { requiresAuth: true } },
      {
        path: "/agents/:agentInstanceId",
        name: "chat",
        component: ChatView,
        meta: { requiresAuth: true },
      },
    ],
  });
  router.beforeEach((to) => {
    const token = localStorage.getItem("token");
    if (to.meta.requiresAuth && !token) {
      return { name: "login" };
    }
    return true;
  });
  const wrapper = mount(Root, {
    global: { plugins: [pinia, router] },
  });
  await router.push("/login");
  await router.isReady();
  await flushPromises();
  return { wrapper, router };
}

describe("login to chat loop", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
    login.mockResolvedValue({ token: "tok", user_id: "u1", login_name: "alice" });
    listAgentInstances.mockResolvedValue({ items: [] });
    createAgentInstance.mockResolvedValue({
      agent_instance_id: "id-1",
      title: "助手A",
      intro: "日常运营",
      agent_mode: "single",
    });
    openAgentInstance.mockResolvedValue({
      agent_instance_id: "id-1",
      thread_id: "thread-1",
      updated_at: "2026-01-01T00:00:00",
    });
    getAgentSidebar.mockResolvedValue({
      title: "助手A",
      capability_description: "规划抖音运营并触达线索",
      development_notes: "能力只展示不勾选",
      agent_mode: "single",
      agent_mode_label: "单智能体模式",
      knowledge_documents: [{ title: "faq", filename: "faq.md" }],
      workflows: [{ code: "douyin-lead-discovery", display_name: "抖音线索发现与触达" }],
      tools: [{ name: "discover_douyin_leads", display_name: "抖音线索发现" }],
    });
    getThread.mockResolvedValue({ status: "idle", interrupt: null, messages: [] });
    fetchAuthBlob.mockRejectedValue(new Error("no avatar"));
  });

  it("runs login -> create modal -> card -> chat", async () => {
    const { wrapper, router } = await mountApp();
    expect(wrapper.text()).toContain("登录");
    await wrapper.get(".agent-login input").setValue("alice");
    await wrapper.get('.agent-login input[type="password"]').setValue("password123");
    await wrapper.get(".agent-login form").trigger("submit");
    await flushPromises();
    expect(login).toHaveBeenCalled();
    expect(localStorage.getItem("token")).toBe("tok");
    await router.push("/agents");
    await flushPromises();
    expect(wrapper.text()).toContain("我的智能体");
    await wrapper.get(".agent-create-btn").trigger("click");
    expect(wrapper.text()).toContain("抖音运营助手");
    await wrapper.get(".agent-template").trigger("click");
    listAgentInstances.mockResolvedValue({
      items: [
        {
          agent_instance_id: "id-1",
          title: "助手A",
          intro: "日常运营",
          agent_mode: "single",
          created_at: "2026-01-01T00:00:00",
          updated_at: "2026-01-02T00:00:00",
        },
      ],
    });
    await wrapper.get(".agent-modal input").setValue("助手A");
    await wrapper.get(".agent-modal textarea").setValue("日常运营");
    await wrapper.get(".agent-modal form").trigger("submit");
    await flushPromises();
    expect(createAgentInstance).toHaveBeenCalledWith("助手A", "日常运营", null);
    expect(wrapper.text()).toContain("助手A");
    expect(wrapper.text()).toContain("单智能体模式");
    await wrapper.get(".agent-card-main").trigger("click");
    await flushPromises();
    expect(openAgentInstance).toHaveBeenCalledWith("id-1");
    expect(wrapper.text()).toContain("抖音线索发现与触达");
    expect(wrapper.text()).toContain("返回广场");
    expect(wrapper.get("textarea").attributes("disabled")).toBeUndefined();
  });

  it("edits and archives a card without opening chat", async () => {
    listAgentInstances.mockResolvedValue({
      items: [
        {
          agent_instance_id: "id-1",
          title: "助手A",
          intro: "日常运营",
          agent_mode: "single",
          created_at: "2026-01-01T00:00:00",
          updated_at: "2026-01-02T00:00:00",
        },
      ],
    });
    patchAgentInstance.mockResolvedValue({ agent_instance_id: "id-1", title: "助手B" });
    archiveAgentInstance.mockResolvedValue({ ok: true, agent_instance_id: "id-1", status: "archived" });
    localStorage.setItem("token", "tok");
    const { wrapper, router } = await mountApp();
    await router.push("/agents");
    await flushPromises();
    expect(wrapper.text()).toContain("助手A");
    await wrapper.get(".agent-card-edit").trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("编辑智能体");
    expect(wrapper.find(".agent-template").exists()).toBe(false);
    await wrapper.get(".agent-modal input").setValue("助手B");
    await wrapper.get(".agent-modal form").trigger("submit");
    await flushPromises();
    expect(patchAgentInstance).toHaveBeenCalledWith("id-1", { title: "助手B", intro: "日常运营" });
    expect(Object.keys(patchAgentInstance.mock.calls[0][1]).sort()).toEqual(["intro", "title"]);
    expect(openAgentInstance).not.toHaveBeenCalled();
    await wrapper.get(".agent-card-archive").trigger("click");
    await wrapper.get(".agent-archive-cancel").trigger("click");
    expect(archiveAgentInstance).not.toHaveBeenCalled();
    listAgentInstances.mockResolvedValue({ items: [] });
    await wrapper.get(".agent-card-archive").trigger("click");
    await wrapper.get(".agent-archive-confirm").trigger("click");
    await flushPromises();
    expect(archiveAgentInstance).toHaveBeenCalledWith("id-1");
    expect(openAgentInstance).not.toHaveBeenCalled();
    expect(wrapper.text()).not.toContain("助手A");
  });
});
