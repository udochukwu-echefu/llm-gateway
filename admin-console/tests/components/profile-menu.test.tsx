import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import { ProfileMenu } from "@/components/profile-menu";
import { PreferencesProvider } from "@/components/preferences";
import { UnsavedPolicies, useUnsavedPolicy } from "@/components/unsaved-policy";
import { browserApi } from "@/lib/browser-api";
import { navigateProfileDocument } from "@/components/profile-session";
import type { Identity } from "@/lib/contracts";

vi.mock("@/lib/browser-api", () => {
  const browserApi = vi.fn();
  return { browserApi, browserSessionApi: browserApi };
});
vi.mock("@/components/profile-session", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/components/profile-session")>()),
  navigateProfileDocument: vi.fn(),
}));
const identity: Identity = {
  key_id: "public-id",
  name: "Demo visitor · Platform viewer",
  role: "viewer",
  organization: null,
};
const demo = { enabled: true, org: true };
beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  vi.stubGlobal(
    "matchMedia",
    vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })),
  );
});
function mount(options: { account?: Identity; availability?: typeof demo; dirty?: boolean } = {}) {
  return render(
    <PreferencesProvider>
      <UnsavedPolicies>
        {options.dirty && <DirtyPolicy />}
        <ProfileMenu identity={options.account ?? identity} demo={options.availability ?? demo} />
        <button>Outside</button>
      </UnsavedPolicies>
    </PreferencesProvider>,
  );
}
function DirtyPolicy() {
  useUnsavedPolicy("test-policy", true);
  return null;
}
function trigger() {
  return screen.getByRole("button", { name: /^Profile menu:/ });
}
function open() {
  fireEvent.click(trigger());
}
function choice(name: string) {
  return screen.getByRole("button", { name: new RegExp(`^${name}`) });
}

test("collapsed actions are not announced; disclosure, Escape focus and outside dismissal work", () => {
  mount();
  expect(trigger().getAttribute("aria-expanded")).toBe("false");
  expect(screen.queryByRole("button", { name: "Sign out" })).toBeNull();

  open();
  expect(trigger().getAttribute("aria-expanded")).toBe("true");
  expect(document.getElementById(trigger().getAttribute("aria-controls")!)).not.toBeNull();
  fireEvent.keyDown(document, { key: "Escape" });
  expect(document.activeElement).toBe(trigger());
  expect(trigger().getAttribute("aria-expanded")).toBe("false");
  open();
  fireEvent.pointerDown(screen.getByRole("button", { name: "Outside" }));
  expect(trigger().getAttribute("aria-expanded")).toBe("false");
});

test("mouse preview closes on exit; a click pins it; touch never relies on hover", async () => {
  vi.useFakeTimers();
  mount();
  const root = document.querySelector(".profile-slot")!;
  const enter = (pointerType: string) =>
    fireEvent(root, Object.assign(new Event("pointerover", { bubbles: true }), { pointerType }));

  enter("touch");
  expect(trigger().getAttribute("aria-expanded")).toBe("false");
  enter("mouse");
  expect(trigger().getAttribute("aria-expanded")).toBe("true");
  fireEvent.pointerOut(root);
  act(() => vi.runAllTimers());
  expect(trigger().getAttribute("aria-expanded")).toBe("false");
  enter("mouse");
  fireEvent.focus(trigger());
  open();
  fireEvent.pointerOut(root);
  act(() => vi.runAllTimers());
  expect(trigger().getAttribute("aria-expanded")).toBe("true");
  vi.useRealTimers();
});

test("current profile is marked and selecting it performs no auth request", () => {
  mount();
  open();
  const selected = choice("Platform viewer");
  expect(selected.getAttribute("aria-pressed")).toBe("true");
  expect(within(selected).getByText("Current profile")).not.toBeNull();

  fireEvent.click(selected);

  expect(browserApi).not.toHaveBeenCalled();
  expect(navigateProfileDocument).not.toHaveBeenCalled();
});

test("switch posts the chosen scope exactly once and replaces the document only after success", async () => {
  let finish!: (value: unknown) => void;
  vi.mocked(browserApi).mockReturnValue(
    new Promise((resolve) => {
      finish = resolve;
    }),
  );
  mount();
  open();

  fireEvent.click(choice("Northwind Health viewer"));
  fireEvent.click(choice("Northwind Health viewer"));

  expect(browserApi).toHaveBeenCalledTimes(1);
  expect(browserApi).toHaveBeenCalledWith("/api/auth/demo", {
    method: "POST",
    body: '{"as":"org"}',
  });
  expect(choice("Platform viewer").getAttribute("aria-pressed")).toBe("true");
  fireEvent.blur(choice("Northwind Health viewer"), { relatedTarget: null });
  expect(trigger().getAttribute("aria-expanded")).toBe("true");
  expect(choice("Northwind Health viewer").hasAttribute("disabled")).toBe(true);
  expect(screen.getByText("Switching…")).not.toBeNull();
  expect(navigateProfileDocument).not.toHaveBeenCalled();
  await act(async () => finish({}));
  expect(navigateProfileDocument).toHaveBeenCalledWith("/overview");
});

for (const message of [
  "Too many sign-in attempts. Please try again in a minute.",
  "The demo is unavailable. Please try again later.",
  "Network connection lost.",
]) {
  test(`${message} preserves identity and unlocks retry without signing out`, async () => {
    vi.mocked(browserApi).mockRejectedValue(new Error(message));
    mount();
    open();

    fireEvent.click(choice("Northwind Health viewer"));

    expect((await screen.findByRole("alert")).textContent).toContain(message);
    expect(choice("Northwind Health viewer").hasAttribute("disabled")).toBe(false);
    expect(choice("Platform viewer").getAttribute("aria-pressed")).toBe("true");
    expect(navigateProfileDocument).not.toHaveBeenCalled();
    expect(browserApi).not.toHaveBeenCalledWith("/api/auth/logout", expect.anything());
  });
}

for (const action of ["Northwind Health viewer", "Sign out"]) {
  test(`${action} respects the unsaved-policy guard`, () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    mount({ dirty: true });
    open();

    fireEvent.click(choice(action));

    expect(confirm).toHaveBeenCalledWith(
      "You have unsaved policy changes. Discard them and leave?",
    );
    expect(browserApi).not.toHaveBeenCalled();
    confirm.mockRestore();
  });
}

test("sign out uses the existing server route and full login navigation", async () => {
  vi.mocked(browserApi).mockResolvedValue({});
  mount();
  open();

  await act(async () => fireEvent.click(choice("Sign out")));

  expect(browserApi).toHaveBeenCalledWith("/api/auth/logout", { method: "POST" });
  expect(navigateProfileDocument).toHaveBeenCalledWith("/login");
});

test("a normal viewer is not mistaken for a publicly switchable demo", () => {
  mount({ availability: { enabled: false, org: false } });
  open();

  expect(screen.queryByRole("region", { name: "Demo profiles" })).toBeNull();
  expect(screen.queryByRole("button", { name: /^Northwind Health viewer/ })).toBeNull();
  expect(screen.getByRole("link", { name: "View profile" }).getAttribute("href")).toBe("/settings");
  expect(choice("Sign out")).not.toBeNull();
});

test("missing org capability omits its profile without inventing a sign-in option", () => {
  mount({ availability: { enabled: true, org: false } });
  open();

  expect(choice("Platform viewer")).not.toBeNull();
  expect(screen.queryByRole("button", { name: /^Northwind Health viewer/ })).toBeNull();
});

test("Northwind identity and current selection come from the authenticated scope", () => {
  mount({
    account: {
      ...identity,
      name: "Demo visitor · Northwind Health viewer",
      organization: { id: "org-id", name: "Northwind Health" },
    },
  });
  open();

  expect(trigger().getAttribute("aria-label")).toBe("Profile menu: Northwind Health viewer");
  expect(choice("Northwind Health viewer").getAttribute("aria-pressed")).toBe("true");
  expect(choice("Platform viewer").getAttribute("aria-pressed")).toBe("false");
});

test("Light Dark System use the existing preference store without admin requests", async () => {
  mount();
  open();
  await act(async () => {});
  for (const theme of ["Dark", "Light", "System"]) {
    fireEvent.click(choice(theme));
    expect(choice(theme).getAttribute("aria-pressed")).toBe("true");
    expect(document.documentElement.dataset.theme).toBe(theme.toLowerCase());
    expect(JSON.parse(localStorage.getItem("gateway-console-preferences")!).theme).toBe(
      theme.toLowerCase(),
    );
  }
  expect(browserApi).not.toHaveBeenCalled();
});

for (const reduced of [false, true]) {
  test(`shared highlight moves without inline styles and respects reduced motion (${reduced})`, () => {
    vi.stubGlobal(
      "matchMedia",
      vi.fn(() => ({ matches: reduced, addEventListener: vi.fn(), removeEventListener: vi.fn() })),
    );
    const cancel = vi.fn();
    const animate = vi.fn(() => ({ cancel }));
    Object.defineProperty(Element.prototype, "animate", { configurable: true, value: animate });
    const view = mount();
    open();
    const row = screen.getByRole("link", { name: "Requests" });
    for (const [name, value] of Object.entries({
      offsetLeft: 8,
      offsetTop: 64,
      offsetWidth: 342,
      offsetHeight: 32,
    })) {
      Object.defineProperty(row, name, { value });
    }

    fireEvent.pointerOver(row);

    expect(animate).toHaveBeenLastCalledWith(
      expect.arrayContaining([
        expect.objectContaining({
          transform: "translate(8px, 64px)",
          width: "342px",
          height: "32px",
        }),
      ]),
      expect.objectContaining({ duration: reduced ? 0 : 250 }),
    );
    expect(document.querySelector(".profile-highlight")?.getAttribute("style")).toBeNull();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(cancel).toHaveBeenCalled();
    view.unmount();
    Reflect.deleteProperty(Element.prototype, "animate");
  });
}

test("expanded card clamps to the phone viewport and gives its actions a bounded scroll region", () => {
  const width = window.innerWidth;
  const height = window.innerHeight;
  Object.defineProperty(window, "innerWidth", { configurable: true, value: 375 });
  Object.defineProperty(window, "innerHeight", { configurable: true, value: 420 });
  const cancel = vi.fn();
  const animate = vi.fn(() => ({ cancel }));
  Object.defineProperty(Element.prototype, "animate", { configurable: true, value: animate });
  const view = mount();
  const slot = document.querySelector(".profile-slot")!;
  vi.spyOn(slot, "getBoundingClientRect").mockReturnValue({
    top: 370,
    bottom: 430,
    left: 280,
    right: 340,
    width: 60,
    height: 60,
    x: 280,
    y: 370,
    toJSON: () => ({}),
  });
  Object.defineProperty(document.querySelector(".profile-scroll"), "scrollHeight", { value: 500 });

  open();

  expect(animate).toHaveBeenCalledWith(
    { top: "16px", left: "16px" },
    { duration: 0, fill: "both" },
  );
  expect(animate).toHaveBeenCalledWith({ maxHeight: "326px" }, { duration: 0, fill: "both" });
  expect(document.querySelector(".profile-card")?.getAttribute("style")).toBeNull();
  view.unmount();
  expect(cancel).toHaveBeenCalled();
  Reflect.deleteProperty(Element.prototype, "animate");
  Object.defineProperty(window, "innerWidth", { configurable: true, value: width });
  Object.defineProperty(window, "innerHeight", { configurable: true, value: height });
});
