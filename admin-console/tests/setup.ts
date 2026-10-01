import { afterEach, vi } from "vitest";
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/fake-test",
  useSearchParams: () => new URLSearchParams(),
}));
import { cleanup } from "@testing-library/react";
afterEach(cleanup);
