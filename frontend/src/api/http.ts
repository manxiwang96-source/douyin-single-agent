import axios, { type AxiosInstance } from "axios";

export const TOKEN_KEY = "token";
export const USER_ID_KEY = "user_id";
export const LOGIN_NAME_KEY = "login_name";
export const HTTP_TIMEOUT_MS = 180000;
export const CHAT_TIMEOUT_MS = 360000;

export type SessionSnapshot = {
  token: string;
  user_id?: string;
  login_name?: string;
};

export type StorageLike = {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
};

export function memoryStorage(initial: Record<string, string> = {}): StorageLike {
  const data = { ...initial };
  return {
    getItem(key) {
      return Object.prototype.hasOwnProperty.call(data, key) ? data[key] : null;
    },
    setItem(key, value) {
      data[key] = value;
    },
    removeItem(key) {
      delete data[key];
    },
  };
}

export function defaultStorage(): StorageLike {
  if (typeof localStorage === "undefined") {
    return memoryStorage();
  }
  return localStorage;
}

export function readToken(storage: StorageLike = defaultStorage()): string {
  return storage.getItem(TOKEN_KEY) || "";
}

export function writeSession(session: SessionSnapshot, storage: StorageLike = defaultStorage()): void {
  storage.setItem(TOKEN_KEY, session.token);
  if (session.user_id) {
    storage.setItem(USER_ID_KEY, session.user_id);
  }
  if (session.login_name) {
    storage.setItem(LOGIN_NAME_KEY, session.login_name);
  }
}

export function clearSession(storage: StorageLike = defaultStorage()): void {
  storage.removeItem(TOKEN_KEY);
  storage.removeItem(USER_ID_KEY);
  storage.removeItem(LOGIN_NAME_KEY);
}

export function authHeaders(token: string): Record<string, string> {
  if (!token) {
    return {};
  }
  return { Authorization: `Bearer ${token}` };
}

export type HttpClientOptions = {
  baseURL?: string;
  getToken?: () => string;
  onUnauthorized?: () => void;
  storage?: StorageLike;
  timeout?: number;
};

export function resolveApiBase(explicit?: string): string {
  if (explicit !== undefined) {
    return explicit;
  }
  const envBase = (import.meta as ImportMeta).env?.VITE_API_BASE;
  return envBase ?? "";
}

export function createHttpClient(options: HttpClientOptions = {}): AxiosInstance {
  const storage = options.storage || defaultStorage();
  const client = axios.create({
    baseURL: resolveApiBase(options.baseURL),
    timeout: options.timeout ?? HTTP_TIMEOUT_MS,
  });
  client.interceptors.request.use((config) => {
    const token = options.getToken ? options.getToken() : readToken(storage);
    const headers = authHeaders(token);
    if (headers.Authorization) {
      config.headers = config.headers || {};
      config.headers.Authorization = headers.Authorization;
    }
    return config;
  });
  client.interceptors.response.use(
    (response) => response,
    (error) => {
      if (axios.isAxiosError(error) && error.response?.status === 401) {
        clearSession(storage);
        options.onUnauthorized?.();
      }
      return Promise.reject(error);
    },
  );
  return client;
}

export const http = createHttpClient();
export const chatHttp = createHttpClient({ timeout: CHAT_TIMEOUT_MS });
