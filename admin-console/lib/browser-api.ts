/* Full navigation after auth changes discards the old page and any one-time key in memory. */
/* eslint-disable @next/next/no-location-assign-relative-destination */
const pendingResponses = new Set<Promise<unknown>>();
let sessionTransition: Promise<void> | undefined;

/** Old reads refresh the encrypted cookie; finish them before changing its identity. */
export function waitForBrowserResponses(): Promise<void> | undefined {
  if (pendingResponses.size) return drainResponses();
}

export class BrowserApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
  }
}
export function browserApi<T>(path: string, init: RequestInit = {}): Promise<T> {
  if (sessionTransition) return sessionTransition.then(() => browserApi<T>(path, init));
  const pending = readBrowserResponse<T>(path, init);
  pendingResponses.add(pending);
  void pending.then(
    () => pendingResponses.delete(pending),
    () => pendingResponses.delete(pending),
  );
  return pending;
}

/** Success retires this document; failure resumes its deferred reads. */
export async function browserSessionApi<T>(path: string, init: RequestInit): Promise<T> {
  if (sessionTransition) throw new Error("A session change is already in progress.");
  let resume!: () => void;
  sessionTransition = new Promise<void>((resolve) => {
    resume = resolve;
  });
  try {
    const pending = waitForBrowserResponses();
    if (pending) await pending;
    return await readBrowserResponse<T>(path, init);
  } catch (error) {
    sessionTransition = undefined;
    resume();
    throw error;
  }
}

async function readBrowserResponse<T>(path: string, init: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    cache: "no-store",
    headers: { "Content-Type": "application/json", ...init.headers },
  });
  const body = await response.json();
  if (response.status === 401) {
    window.location.assign("/login");
    throw new Error("Please sign in again.");
  }
  if (!response.ok) throw new BrowserApiError(response.status, body.error || "The request failed.");
  if (
    init.method &&
    ["PUT", "DELETE", "POST"].includes(init.method) &&
    path.startsWith("/api/admin") &&
    !path.endsWith("/keys")
  )
    window.dispatchEvent(new Event("console-saved"));
  return body as T;
}

async function drainResponses() {
  while (pendingResponses.size) await Promise.allSettled([...pendingResponses]);
}
