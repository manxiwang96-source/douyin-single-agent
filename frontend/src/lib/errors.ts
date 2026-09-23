import axios from "axios";

const DETAIL_MAP: Record<string, string> = {
  "title already in use": "名称已被使用",
  "login_name already exists": "登录名已被使用",
  "invalid credentials": "账号或密码错误",
  "user is disabled": "用户已停用",
  "not authenticated": "请先登录",
  "thread is waiting for review": "当前需要审核后才能继续",
  "title must not be blank": "名称不能为空",
  "title must not contain whitespace": "名称不能包含空白字符",
  "agent instance not found": "该智能体不存在或已归档",
};

export class ChatHttpError extends Error {
  status: number;
  detail: string;
  code?: string;

  constructor(status: number, detail: string, code?: string) {
    super(detail);
    this.name = "ChatHttpError";
    this.status = status;
    this.detail = detail;
    this.code = code;
  }
}

function mappedDetail(detail: unknown, code?: string): string | null {
  if (typeof detail === "string" && detail) {
    return DETAIL_MAP[detail] || detail;
  }
  if (code === "ECONNABORTED") {
    return "请求超时，请稍后重试";
  }
  return null;
}

export function apiErrorMessage(error: unknown, fallback = "请求失败，请重试"): string {
  if (error instanceof ChatHttpError) {
    return mappedDetail(error.detail, error.code) || fallback;
  }
  if (axios.isAxiosError(error)) {
    const mapped = mappedDetail(error.response?.data?.detail, error.code);
    if (mapped) return mapped;
  }
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return fallback;
}
