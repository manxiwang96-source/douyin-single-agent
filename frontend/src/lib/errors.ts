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

export function apiErrorMessage(error: unknown, fallback = "请求失败，请重试"): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    if (typeof detail === "string" && detail) {
      return DETAIL_MAP[detail] || detail;
    }
    if (error.code === "ECONNABORTED") {
      return "请求超时，请稍后重试";
    }
  }
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return fallback;
}
