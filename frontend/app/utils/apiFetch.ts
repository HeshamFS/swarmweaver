/**
 * Centralized API fetch wrapper that replaces silent catch {} blocks.
 * Shows toast notifications for failed user-initiated actions.
 * Background polls should pass silent=true.
 */

type ToastFn = (type: "error" | "info" | "success", title: string, body?: string) => void;

export async function apiFetch(
  url: string,
  options?: RequestInit,
  addToast?: ToastFn,
  silent: boolean = false
): Promise<Response | null> {
  try {
    const res = await fetch(url, options);
    if (!res.ok && !silent && addToast) {
      const status = res.status;
      const endpoint = url.split("?")[0].replace(/^\/api\//, "");
      addToast("error", `API Error (${status})`, `Failed: ${endpoint}`);
    }
    return res;
  } catch {
    if (!silent && addToast) {
      addToast("error", "Network Error", "Backend may not be running");
    }
    return null;
  }
}

/**
 * Convenience wrapper that parses JSON response.
 */
export async function apiFetchJson<T = Record<string, unknown>>(
  url: string,
  options?: RequestInit,
  addToast?: ToastFn,
  silent: boolean = false
): Promise<T | null> {
  const res = await apiFetch(url, options, addToast, silent);
  if (!res) return null;
  try {
    return (await res.json()) as T;
  } catch {
    if (!silent && addToast) {
      addToast("error", "Parse Error", "Invalid response from server");
    }
    return null;
  }
}
