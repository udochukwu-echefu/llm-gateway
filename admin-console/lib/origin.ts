export function hasSameOrigin(request: Request, expected: string): boolean {
  // Trust deployment configuration, never attacker-controlled Host / forwarded headers.
  return request.headers.get("origin") === new URL(expected).origin;
}
