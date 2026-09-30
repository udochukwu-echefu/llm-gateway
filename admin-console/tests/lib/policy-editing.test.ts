import { expect, test } from "vitest";
import {
  modelPolicySchema,
  guardrailsSchema,
  residencySchema,
  ifMatchSchema,
  policyHeaders,
} from "@/lib/policy-schemas";
import { listChanges, guardrailChanges, noEffect, weakensGuardrails } from "@/lib/policy-changes";
import { operationSchema, isCreation } from "@/lib/bff-policy";
const defaults = {
  secret_api_key: "block",
  secret_private_key: "block",
  email: "allow",
  phone: "allow",
  card_number: "redact",
  iban: "redact",
  ip_address: "allow",
} as const;
test("strict policy schemas reject unknown detectors actions regions and bad patterns", () => {
  for (const actions of [
    ["unknown=allow"],
    ["email=unknown"],
    ["email=allow", "email=block"],
    ["email=allow=block"],
  ])
    expect(guardrailsSchema.safeParse({ actions }).success).toBe(false);
  for (const regions of [["mars"], Array(6).fill("eu")])
    expect(residencySchema.safeParse({ regions }).success).toBe(false);
  for (const allow of [["fast"], ["groq/**"], ["groq/../x"], Array(257).fill("groq/*")])
    expect(modelPolicySchema.safeParse({ allow }).success).toBe(false);
  expect(guardrailsSchema.safeParse({ actions: Array(8).fill("email=allow") }).success).toBe(false);
  expect(modelPolicySchema.safeParse({ allow: [], unexpected: true }).success).toBe(false);
  expect(modelPolicySchema.parse({ allow: ["groq/*", "groq/*"] }).allow).toEqual(["groq/*"]);
  expect(residencySchema.parse({ regions: ["eu", "eu"] }).regions).toEqual(["eu"]);
});
test("policy writes require a quoted version and other routes never forward it", () => {
  for (const value of ["*", "short", "a".repeat(64), 'W/"' + "a".repeat(64) + '"'])
    expect(ifMatchSchema.safeParse(value).success).toBe(false);
  const version = '"' + "a".repeat(64) + '"';
  expect(policyHeaders("PUT", "/orgs/fake/guardrails", version)).toEqual({ "If-Match": version });
  expect(policyHeaders("DELETE", "/orgs/fake/residency", null)).toBeNull();
  expect(policyHeaders("POST", "/orgs/fake/cache/purge", version)).toEqual({});
  expect(isCreation("POST", "/orgs/fake/cache/purge")).toBe(false);
  expect(operationSchema("GET", "/catalog")).toBeNull();
  expect(operationSchema("PUT", "/orgs/fake/guardrails")).toBe(guardrailsSchema);
});
test("change summaries distinguish inherit deny-all additions removals and actions", () => {
  expect(listChanges(null, [])).toEqual(["Allow nothing → block every model at this level"]);
  expect(listChanges([], null)).toEqual(["Remove override → no restriction at this level"]);
  expect(listChanges(["eu"], ["us"])).toEqual(["Added: us", "Removed: eu"]);
  expect(listChanges(["us", "eu"], ["eu", "us"])).toEqual([]);
  expect(guardrailChanges({ email: "block" }, { email: "redact" })).toEqual([
    "email: block → redact",
  ]);
  expect(weakensGuardrails({ email: "block" }, { email: "redact" })).toBe(true);
  expect(weakensGuardrails({ email: "block" }, {})).toBe(true);
  expect(weakensGuardrails({}, { email: "block" })).toBe(false);
});
test("no effect warnings identify the inherited floor", () => {
  expect(noEffect("email", "allow", defaults, { email: "block" })).toBe(
    "No effect: the organisation already requires block",
  );
  expect(noEffect("card_number", "allow", defaults)).toBe(
    "No effect: the built-in default already requires redact",
  );
  expect(noEffect("email", "block", defaults, { email: "block" })).toBe("");
});
