import { http } from "./http";

export type AuthUser = {
  user_id: string;
  login_name: string;
};

export type LoginResult = AuthUser & { token: string };

export async function register(loginName: string, password: string): Promise<AuthUser> {
  const response = await http.post("/v1/auth/register", {
    login_name: loginName,
    password,
  });
  return response.data;
}

export async function login(loginName: string, password: string): Promise<LoginResult> {
  const response = await http.post("/v1/auth/login", {
    login_name: loginName,
    password,
  });
  return response.data;
}

export async function logout(): Promise<void> {
  await http.post("/v1/auth/logout");
}

export async function me(): Promise<AuthUser> {
  const response = await http.get("/v1/me");
  return response.data;
}
