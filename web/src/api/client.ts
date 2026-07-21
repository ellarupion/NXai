// Тонкий fetch-враппер: JWT из localStorage в каждый запрос, единая обработка 401
// (сбрасывает сессию — тот же токен больше нигде не валиден, ретраить нечего).
// Адаптировано из NX web/src/api/client.ts почти без изменений.

export const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
const TOKEN_KEY = "nxai_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function handleResponse<T>(response: Response, hadToken: boolean): Promise<T> {
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail ?? detail;
    } catch {
      // тело не JSON — оставляем statusText
    }
    // Сбрасываем сессию только если 401 пришёл на запрос С токеном (значит, сама
    // сессия умерла) — 401 на /auth/login без токена значит просто "неверный
    // логин/пароль", не должен затирать сообщение бэкенда generic-текстом.
    if (response.status === 401 && hadToken) {
      clearToken();
      window.dispatchEvent(new Event("nxai-unauthorized"));
    }
    throw new ApiError(response.status, typeof detail === "string" ? detail : response.statusText);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers = new Headers(options.headers);
  headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const response = await fetch(`${API_URL}${path}`, { ...options, headers });
  return handleResponse<T>(response, Boolean(token));
}

// Тянет бинарный ответ (например, превью медиа) с тем же токеном и возвращает
// object URL для <img src>. img не умеет слать Authorization-заголовок, поэтому
// качаем через fetch как blob. Вызывающий обязан URL.revokeObjectURL после.
async function getObjectUrl(path: string): Promise<string> {
  const token = getToken();
  const headers = new Headers();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(`${API_URL}${path}`, { headers });
  if (!response.ok) {
    throw new ApiError(response.status, response.statusText);
  }
  const blob = await response.blob();
  return URL.createObjectURL(blob);
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) }),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PUT", body: body === undefined ? undefined : JSON.stringify(body) }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
  getObjectUrl,
};
