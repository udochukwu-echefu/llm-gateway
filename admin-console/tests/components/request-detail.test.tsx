import { render, screen } from "@testing-library/react";
import { beforeAll, expect, test, vi } from "vitest";
import { RequestDetail } from "@/components/request-detail";

vi.mock("@/components/use-resource", () => ({
  useResource: () => ({
    data: {
      data: [
        {
          id: "fake",
          request_id: "fake-request",
          attempt: 1,
          provider: "groq",
          status_code: 200,
          outcome: "success",
          model: "fake-model",
          duration_ms: 1724.9999999999998,
          ttfb_ms: 50599.99999999999,
          prompt_tokens: 1234567,
          completion_tokens: null,
          cost_usd: null,
          cost_status: "unpriced",
          redaction_count: null,
          key_id: "fake-key",
          created_at: "2026-10-01T00:00:00Z",
        },
      ],
    },
    loading: false,
  }),
}));
beforeAll(() => {
  HTMLDialogElement.prototype.showModal = function () {
    this.setAttribute("open", "");
  };
  HTMLDialogElement.prototype.close = function () {
    this.removeAttribute("open");
  };
});
test("request timeline uses readable duration and token units while retaining Unknown", () => {
  render(<RequestDetail org="Fake" id="fake-request" onClose={() => {}} />);
  expect(screen.getByText("1,725 ms / 50.6 s")).toBeDefined();
  expect(screen.getByText("1,234,567 / Unknown")).toBeDefined();
});
