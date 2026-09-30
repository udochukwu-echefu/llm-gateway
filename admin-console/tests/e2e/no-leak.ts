import type { Page, Request } from "@playwright/test";
import { expect } from "@playwright/test";
export async function responseScanner(page: Page) {
  const records = new Map<Request, { url: string; method: string; body: string; headers: string }>();
  const failures: string[] = [];
  const received = new Set<Request>();
  const pending: Promise<void>[] = [];
  page.on("response", (response) => {
    received.add(response.request());
    if (records.has(response.request())) return;
    // Chromium may follow a redirect without invoking the route handler again.
    // Read those responses immediately, before later navigation can evict them.
    pending.push((async () => {
      try {
        const body = (await response.body()).toString("utf8");
        records.set(response.request(), { url: response.url(), method: response.request().method(), body, headers: JSON.stringify(await response.allHeaders()) });
      } catch { failures.push(response.url()); }
    })());
  });
  // Capture complete bytes before fulfillment: browser navigations otherwise evict
  // old response bodies from Chromium's protocol cache. No response is exempted.
  await page.route("**/*", async (route) => {
    try {
      const upstream = await route.fetch({ maxRedirects: 0 });
      const body = await upstream.body();
      const record = { url: route.request().url(), method: route.request().method(), body: body.toString("utf8"), headers: JSON.stringify(upstream.headersArray()) };
      records.set(route.request(), record);
      await route.fulfill({ response: upstream, body });
    }
    catch {
      failures.push(route.request().url());
      await route.abort();
    }
  });
  return {
    async verify(adminKeys: string[], tenantKeys: string[], permittedKey?: string) {
      await page.waitForLoadState("networkidle");
      await Promise.all(pending);
      expect(failures.length, "Every browser response must be inspected").toBe(0);
      // Captured requests cancelled before a response are also scanned below.
      for (const request of received)
        expect(records.has(request), "Captured bytes for every response received by the browser").toBe(true);
      let oneTimeResponses = 0;
      for (const record of records.values()) {
        const text = record.body + record.headers;
        expect(/lgwa_[A-Za-z0-9_-]{12,}/.test(text), `Admin credential in response from ${record.url}`).toBe(false);
        for (const key of adminKeys)
          expect(text.includes(key), "Admin key must never reach a response").toBe(false);
        const keys = new Set([
          ...tenantKeys, ...(text.match(/lgw_[a-z2-7]{12}_[A-Za-z0-9_-]{43}/g) ?? []),
        ]);
        for (const key of keys) {
          if (!text.includes(key)) continue;
          const permitted = key === permittedKey && record.method === "POST"
            && new URL(record.url).pathname.endsWith("/keys");
          expect(permitted, "Tenant secret leaked outside its creation response").toBe(true);
          expect(record.headers.includes(key), "Tenant secret in headers").toBe(false);
          const body = JSON.parse(record.body);
          expect(body.key === key).toBe(true);
          const { key: _key, ...rest } = body;
          void _key;
          expect(JSON.stringify(rest).includes(key)).toBe(false);
          oneTimeResponses++;
        }
      }
      expect(oneTimeResponses, "Exactly one first-creation response may contain the tenant secret").toBe(permittedKey ? 1 : 0);
      console.log(`No-leak scan: ${received.size} browser responses; ${oneTimeResponses} permitted key-creation response; zero leaks.`);
      return { responses: received.size, permitted: oneTimeResponses };
    }
  };
}
