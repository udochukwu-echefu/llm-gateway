import "server-only";

type Failures = { count: number; expiresAt: number };

// Best effort, per process/replica. Bound memory; no credential is retained.
export class LoginThrottle {
  private readonly failures = new Map<string, Failures>();

  constructor(
    private readonly limit = 10,
    private readonly windowMs = 60000,
    private readonly capacity = 10000,
  ) {}

  retryAfter(client: string, now = Date.now()): number {
    const state = this.failures.get(client);
    if (!state || state.expiresAt <= now) {
      this.failures.delete(client);
      return 0;
    }
    return state.count >= this.limit ? Math.ceil((state.expiresAt - now) / 1000) : 0;
  }

  failed(client: string, now = Date.now()): void {
    let state = this.failures.get(client);
    if (!state || state.expiresAt <= now) {
      if (this.failures.size >= this.capacity) {
        this.failures.delete(this.failures.keys().next().value!);
      }
      state = { count: 0, expiresAt: now + this.windowMs };
      this.failures.set(client, state);
    }
    state.count++;
  }

  succeeded(client: string): void {
    this.failures.delete(client);
  }
}

export const loginThrottle = new LoginThrottle();
