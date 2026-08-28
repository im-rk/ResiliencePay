import { render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuditTrailTable } from "../AuditTrailTable";
import * as apiClient from "../../api/client";
import { vi, test, expect } from "vitest";
import React from "react";

function renderWithClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

test("never renders simulated=null as Real", async () => {
  vi.spyOn(apiClient, "fetchAuditTrail").mockResolvedValue({
    entries: [{
      audit_id: 1, 
      cause_category: "otp_failure", 
      chosen_arm: "retry_immediate",
      gate_result: true, 
      simulated: null, 
      outcome_result: "recovered", 
      recorded_at: "2026-08-20T10:00:00Z"
    } as any],
  });
  renderWithClient(<AuditTrailTable />);
  const cell = await screen.findByText(/otp_failure/i);
  const row = cell.closest("tr")!;
  expect(within(row).queryByText("Real")).not.toBeInTheDocument();
});
