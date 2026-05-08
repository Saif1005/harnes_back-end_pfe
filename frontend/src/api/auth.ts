import { axiosClient } from "@/api/axiosClient";

export interface AuthUserDto {
  id: string;
  email: string;
  name?: string;
  role?: string;
}

export interface AuthTokenDto {
  access_token: string;
  token_type: string;
  user: AuthUserDto;
}

export interface AuthGoogleLoginPayload {
  id_token: string;
}

export interface AuthAdminRegisterPayload {
  email: string;
  password: string;
  name?: string;
  bootstrap_key?: string;
}

export interface AuthAdminForgotPasswordPayload {
  email: string;
  new_password: string;
  bootstrap_key: string;
}

export interface AuthAdminRegistrationStatusDto {
  admin_exists: boolean;
}

export async function registerAuth(payload: {
  email: string;
  password: string;
  name?: string;
}): Promise<AuthTokenDto> {
  const { data } = await axiosClient.post<AuthTokenDto>("/auth/register", payload);
  return data;
}

export async function loginAuth(payload: {
  email: string;
  password: string;
}): Promise<AuthTokenDto> {
  const { data } = await axiosClient.post<AuthTokenDto>("/auth/login", payload);
  return data;
}

export async function meAuth(): Promise<AuthUserDto> {
  const { data } = await axiosClient.get<AuthUserDto>("/auth/me");
  return data;
}

export async function logoutAuth(): Promise<void> {
  await axiosClient.post("/auth/logout");
}

export async function loginGoogleAuth(payload: AuthGoogleLoginPayload): Promise<AuthTokenDto> {
  const { data } = await axiosClient.post<AuthTokenDto>("/auth/google", payload);
  return data;
}

export async function registerAdminAuth(payload: AuthAdminRegisterPayload): Promise<AuthTokenDto> {
  const { data } = await axiosClient.post<AuthTokenDto>("/auth/register/admin", payload);
  return data;
}

export async function getAdminRegistrationStatusAuth(): Promise<AuthAdminRegistrationStatusDto> {
  const { data } = await axiosClient.get<AuthAdminRegistrationStatusDto>("/auth/admin/registration-status");
  return data;
}

export async function forgotAdminPasswordAuth(payload: AuthAdminForgotPasswordPayload): Promise<{ status: string; message: string }> {
  const { data } = await axiosClient.post<{ status: string; message: string }>("/auth/admin/forgot-password", payload);
  return data;
}

