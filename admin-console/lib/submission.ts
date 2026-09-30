export function submissionId() {
  let current: string | undefined;
  return { begin: () => current ??= crypto.randomUUID(), finish: () => { current = undefined; } };
}
