import { createRouter, createWebHistory, type Router, type RouteRecordRaw } from "vue-router";
import { useAuthStore } from "../stores/auth";

export const routes: RouteRecordRaw[] = [
  { path: "/", redirect: "/agents" },
  {
    path: "/login",
    name: "login",
    component: () => import("../views/LoginView.vue"),
    meta: { public: true },
  },
  {
    path: "/agents",
    name: "plaza",
    component: () => import("../views/PlazaView.vue"),
    meta: { requiresAuth: true },
  },
  {
    path: "/agents/:agentInstanceId",
    name: "chat",
    component: () => import("../views/ChatView.vue"),
    meta: { requiresAuth: true },
  },
];

export function createAppRouter(): Router {
  const router = createRouter({
    history: createWebHistory(),
    routes,
  });
  router.beforeEach((to) => {
    const auth = useAuthStore();
    if (to.meta.requiresAuth && !auth.token) {
      return { name: "login", query: { redirect: to.fullPath } };
    }
    if (to.name === "login" && auth.token) {
      return { name: "plaza" };
    }
    return true;
  });
  return router;
}
