import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ExceptionList } from "../ExceptionList";
import * as apiClient from "../../api/client";
import { vi, test, expect } from "vitest";
import React from "react";

function renderWithClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, retryDelay: 0 } } });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

test("renders explicit empty state at zero exceptions", async () => {
  vi.spyOn(apiClient, "fetchExceptions").mockResolvedValue([]);
  renderWithClient(<ExceptionList runId="run-1" />);
  expect(await screen.findByText(/0 unresolved exceptions/i)).toBeInTheDocument();
});

test("renders exception rows at non-zero count", async () => {
  vi.spyOn(apiClient, "fetchExceptions").mockResolvedValue([
    { event_id: "e1", cause_category: "hard_decline", reason: "3 attempts exhausted" } as any,
  ]);
  renderWithClient(<ExceptionList runId="run-1" />);
  expect(await screen.findByText("hard_decline")).toBeInTheDocument();
});

test("renders error state on fetch failure without crashing", async () => {
  vi.spyOn(apiClient, "fetchExceptions").mockRejectedValue(new Error("network error"));
  renderWithClient(<ExceptionList runId="run-1" />);
  expect(await screen.findByText(/could not load exceptions/i)).toBeInTheDocument();
});
