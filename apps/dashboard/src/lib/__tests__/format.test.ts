import { expect, test } from "vitest";
import { formatPaise } from "../format";

test("formats zero as a valid currency value, not a placeholder", () => {
  expect(formatPaise(0)).toBe("₹0.00");
});

test("formats a typical amount correctly", () => {
  expect(formatPaise(149900)).toBe("₹1,499.00");
});
