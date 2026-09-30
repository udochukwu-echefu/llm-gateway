import { expect, test } from "vitest";
import type { Catalog } from "@/lib/policy-contracts";
import { catalogRegions, fallbackRegions } from "@/lib/policy-regions";
import { residencySchemaFor } from "@/lib/policy-schemas";

const models: Catalog["models"] = [
  {
    name: "groq/fake-model",
    provider: "groq",
    region: "test-region",
    endpoints: ["chat"],
    priced: false,
  },
];

test("explicit catalogue regions are authoritative and deduplicated", () => {
  const catalog = { models, aliases: {}, regions: ["eu", "eu", "unknown"] };
  expect(catalogRegions(catalog)).toEqual(["eu", "unknown"]);
  expect(residencySchemaFor(catalog).safeParse({ regions: ["test-region"] }).success).toBe(false);
});
test("older catalogues discover model regions while retaining valid empty regions", () => {
  const catalog = { models: [...models, ...models], aliases: {} };
  expect(catalogRegions(catalog)).toEqual([...fallbackRegions, "test-region"]);
  expect(
    residencySchemaFor(catalog).parse({ regions: ["test-region", "test-region"] }).regions,
  ).toEqual(["test-region"]);
  expect(residencySchemaFor(catalog).safeParse({ regions: ["eu"] }).success).toBe(true);
  expect(residencySchemaFor(catalog).safeParse({ regions: ["not-advertised"] }).success).toBe(
    false,
  );
});
test("an unavailable region list uses exactly the shared five-region fallback", () => {
  expect(catalogRegions()).toEqual(["us", "eu", "cn", "global", "unknown"]);
  expect(catalogRegions({ models: [], aliases: {} })).toEqual(fallbackRegions);
});
test("dynamic schemas retain list bounds strictness and deliberate deny-all", () => {
  const schema = residencySchemaFor({ models, aliases: {}, regions: ["test-region", "eu"] });
  expect(schema.safeParse({ regions: Array(3).fill("eu") }).success).toBe(false);
  expect(schema.safeParse({ regions: [], extra: true }).success).toBe(false);
  expect(schema.parse({ regions: [] })).toEqual({ regions: [] });
  const empty = residencySchemaFor({ models, aliases: {}, regions: [] });
  expect(empty.parse({ regions: [] })).toEqual({ regions: [] });
  expect(empty.safeParse({ regions: ["eu"] }).success).toBe(false);
});
