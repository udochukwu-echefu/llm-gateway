import type { Page } from "@playwright/test";
import { expect } from "@playwright/test";
export async function responseScanner(page: Page) {
  const records: {
    url: string;
    method: string;
    body: string;
    headers: string;
  }[] = [];
  const failures: string[] = [];
  let received = 0;
  page.on("response", () => received++);
  // Capture complete bytes before fulfillment: browser navigations otherwise evict
  // old response bodies from Chromium's protocol cache. No response is exempted.
  await page.route("**/*", async (route) => {
    try {
      const upstream = await route.fetch({ maxRedirects: 0 });
      const body = await upstream.body();
      const record = { url: route.request().url(), method: route.request().method(), body: body.toString("utf8"), headers: JSON.stringify(upstream.headersArray()) };
      records.push(record);
      await route.fulfill({ response: upstream, body });
    }
    catch {
      failures.push(route.request().url());
      await route.abort();
    }
  });
  return {
    async verify(adminKeys: string[], createdKey: string) {
      await page.waitForLoadState("networkidle");
      expect(failures.length, "Every browser response must be inspected").toBe(0);
      expect(records.length, "Captured bytes for every response received by the browser").toBe(received);
      let oneTimeResponses = 0;
      for (const record of records) {
        const text = record.body + record.headers;
        expect(/lgwa_[A-Za-z0-9_-]{12,}/.test(text), `Admin credential in response from ${record.url}`).toBe(false);
        for (const key of adminKeys)
          expect(text.includes(key), "Admin key must never reach a response").toBe(false);
        if (text.includes(createdKey)) {
          const permitted = record.method === "POST" && new URL(record.url).pathname.endsWith("/keys");
          expect(permitted, "Tenant secret leaked outside its creation response").toBe(true);
          expect(record.headers.includes(createdKey), "Tenant secret in headers").toBe(false);
          const body = JSON.parse(record.body);
          expect(body.key === createdKey).toBe(true);
          const { key: _key, ...rest } = body;
          void _key;
          expect(JSON.stringify(rest).includes(createdKey)).toBe(false);
          oneTimeResponses++;
        }
      }
      expect(oneTimeResponses, "Exactly one first-creation response may contain the tenant secret").toBe(1);
      console.log(`No-leak scan: ${records.length} browser responses; one permitted key-creation response; zero leaks.`);
      return records.length;
    }
  };
}
