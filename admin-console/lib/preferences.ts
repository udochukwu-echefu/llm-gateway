import { z } from "zod";
export const preferencesSchema = z
  .object({
    theme: z.enum(["system", "light", "dark"]),
    time: z.enum(["utc", "local"]),
    density: z.enum(["comfortable", "compact"]),
    landing: z.enum(["/overview", "/requests", "/analytics", "/keys", "/models", "/settings"]),
  })
  .strict();
export type Preferences = z.infer<typeof preferencesSchema>;
export const defaultPreferences: Preferences = {
  theme: "system",
  time: "utc",
  density: "comfortable",
  landing: "/overview",
};
export const PREFERENCES_KEY = "gateway-console-preferences";
export function readPreferences(storage: Pick<Storage, "getItem">): Preferences {
  try {
    const parsed = preferencesSchema.safeParse(
      JSON.parse(storage.getItem(PREFERENCES_KEY) ?? "null"),
    );
    return parsed.success ? parsed.data : defaultPreferences;
  } catch {
    return defaultPreferences;
  }
}
export function savePreferences(storage: Pick<Storage, "setItem">, value: Preferences) {
  storage.setItem(PREFERENCES_KEY, JSON.stringify(preferencesSchema.parse(value)));
}
