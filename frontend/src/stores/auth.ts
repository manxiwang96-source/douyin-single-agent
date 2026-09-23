import { defineStore } from "pinia";
import { computed, ref } from "vue";
import { login as loginApi, logout as logoutApi, me as meApi, register as registerApi } from "../api/auth";
import {
  LOGIN_NAME_KEY,
  TOKEN_KEY,
  USER_ID_KEY,
  clearSession,
  defaultStorage,
  writeSession,
} from "../api/http";

export const useAuthStore = defineStore("auth", () => {
  const storage = defaultStorage();
  const token = ref(storage.getItem(TOKEN_KEY) || "");
  const userId = ref(storage.getItem(USER_ID_KEY) || "");
  const loginName = ref(storage.getItem(LOGIN_NAME_KEY) || "");

  const isAuthenticated = computed(() => Boolean(token.value));

  function persist() {
    if (!token.value) {
      clearSession(storage);
      return;
    }
    writeSession(
      { token: token.value, user_id: userId.value, login_name: loginName.value },
      storage,
    );
  }

  function setSession(payload: { token: string; user_id?: string; login_name?: string }) {
    token.value = payload.token;
    userId.value = payload.user_id || "";
    loginName.value = payload.login_name || "";
    persist();
  }

  function clear() {
    token.value = "";
    userId.value = "";
    loginName.value = "";
    persist();
  }

  async function login(name: string, password: string) {
    const result = await loginApi(name, password);
    setSession(result);
    return result;
  }

  async function register(name: string, password: string) {
    await registerApi(name, password);
    return login(name, password);
  }

  async function logout() {
    try {
      if (token.value) {
        await logoutApi();
      }
    } finally {
      clear();
    }
  }

  async function hydrate() {
    if (!token.value) {
      return false;
    }
    try {
      const profile = await meApi();
      userId.value = profile.user_id;
      loginName.value = profile.login_name;
      persist();
      return true;
    } catch {
      clear();
      return false;
    }
  }

  return {
    token,
    userId,
    loginName,
    isAuthenticated,
    setSession,
    clear,
    login,
    register,
    logout,
    hydrate,
  };
});
