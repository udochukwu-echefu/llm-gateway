export const detectors = [
  "secret_api_key",
  "secret_private_key",
  "email",
  "phone",
  "card_number",
  "iban",
  "ip_address",
] as const;
export const actions = ["allow", "redact", "block"] as const;
export type Detector = (typeof detectors)[number];
export type Action = (typeof actions)[number];
export type GuardrailOverrides = Partial<Record<Detector, Action>>;
export interface PolicyView<T, E> {
  version: string;
  overrides: { organization: T; team: T };
  effective: E;
}
export interface EffectiveModels {
  models: string[];
  aliases: string[];
}
export type ListPolicy = PolicyView<string[] | null, EffectiveModels & { regions?: string[] }>;
export type GuardrailView = PolicyView<GuardrailOverrides, Record<Detector, Action>> & {
  defaults: Record<Detector, Action>;
};
export interface Catalog {
  regions?: string[];
  models: {
    name: string;
    provider: string;
    region: string;
    endpoints: string[];
    priced: boolean;
  }[];
  aliases: Record<string, { model: string; weight: number }[]>;
}
export const detectorDescriptions: Record<Detector, string> = {
  secret_api_key: "API keys with recognized prefixes",
  secret_private_key: "Complete private key blocks",
  email: "Email addresses",
  phone: "Phone number patterns",
  card_number: "Payment card numbers with a valid checksum",
  iban: "International bank account numbers with a valid checksum",
  ip_address: "IPv4 and IPv6 addresses",
};
export const regionDescriptions: Record<string, string> = {
  us: "United States",
  eu: "European Union",
  cn: "China",
  global: "The provider may process anywhere",
  unknown: "No verified processing region",
};
