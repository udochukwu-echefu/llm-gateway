import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState, type ReactNode } from "react";
import { expect, test, vi } from "vitest";
import { SearchInput } from "@/components/search-input";
vi.mock("@/components/search-visuals", () => ({
  SearchVisuals: ({ children }: { children: ReactNode }) => children,
}));
const label = "Search pages, organisations, teams and keys";
function Composer({ submit }: { submit: () => void }) {
  const [value, setValue] = useState("");
  return <SearchInput value={value} onChange={setValue} busy={false} onSubmit={submit} />;
}
test("search enables its orb after two characters and submits from the keyboard", async () => {
  const user = userEvent.setup();
  const submit = vi.fn();
  render(<Composer submit={submit} />);
  expect((screen.getByRole("button", { name: "Search" }) as HTMLButtonElement).disabled).toBe(true);
  await user.type(screen.getByLabelText(label), "a");
  expect((screen.getByRole("button", { name: "Search" }) as HTMLButtonElement).disabled).toBe(true);
  await user.type(screen.getByLabelText(label), "b{Enter}");
  expect(submit).toHaveBeenCalledOnce();
  expect((screen.getByRole("button", { name: "Search" }) as HTMLButtonElement).disabled).toBe(
    false,
  );
});
test("Escape clears and blurs the field and slash focuses it again", async () => {
  const user = userEvent.setup();
  render(<Composer submit={vi.fn()} />);
  const input = screen.getByLabelText(label) as HTMLInputElement;
  await user.type(input, "gateway{Escape}");
  expect(input.value).toBe("");
  expect(document.activeElement).not.toBe(input);
  fireEvent.keyDown(window, { key: "/" });
  expect(document.activeElement).toBe(input);
});
