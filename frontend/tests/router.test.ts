import { mount, flushPromises } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it } from "vitest";
import { createMemoryHistory, createRouter, RouterView, type RouteRecordRaw } from "vue-router";
import { defineComponent } from "vue";
import { useAuthStore } from "../src/stores/auth";

const LoginStub = defineComponent({ name: "LoginView", template: "<div>login-page</div>" });
const PlazaStub = defineComponent({ name: "PlazaView", template: "<div>plaza-page</div>" });
const Root = defineComponent({ name: "Root", components: { RouterView }, template: "<RouterView />" });

function makeRouter() {
  const routes: RouteRecordRaw[] = [
    { path: "/login", name: "login", component: LoginStub, meta: { public: true } },
    { path: "/agents", name: "plaza", component: PlazaStub, meta: { requiresAuth: true } },
  ];
  const router = createRouter({ history: createMemoryHistory(), routes });
  router.beforeEach((to) => {
    const auth = useAuthStore();
    if (to.meta.requiresAuth && !auth.token) {
      return { name: "login", query: { redirect: to.fullPath } };
    }
    return true;
  });
  return router;
}

describe("router guard", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("redirects unauthenticated users away from /agents", async () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    const router = makeRouter();
    const wrapper = mount(Root, {
      global: { plugins: [pinia, router] },
    });
    await router.push("/agents");
    await router.isReady();
    await flushPromises();
    expect(router.currentRoute.value.name).toBe("login");
    expect(wrapper.text()).toContain("login-page");
  });
});
