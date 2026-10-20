export async function api<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    credentials: "same-origin",
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (res.status === 401) {
    window.location.href = "/login/";
    throw new Error("unauthorized");
  }
  if (res.status >= 400) throw new Error(`API ${res.status}: ${url}`);
  return (await res.json()) as T;
}
