import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test } from "vitest";
import { UsageEmpty, firstRequest } from "@/components/usage-empty";
test("no usage explains a first request and copies only the placeholder", async () => {
  const user = userEvent.setup();
  render(<UsageEmpty />);
  expect(screen.getByRole("heading", { name: "No usage yet" })).toBeDefined();
  expect(firstRequest).toContain("YOUR_TEAM_API_KEY");
  expect(firstRequest).not.toMatch(/lgwa?_/);
  await user.click(screen.getByText("Copy example request"));
  expect(await navigator.clipboard.readText()).toBe(firstRequest);
  await screen.findByText("Example copied. Replace the placeholder key privately.");
});
