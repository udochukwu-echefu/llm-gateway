import { csvCell } from "@/lib/csv";
import { expect, test } from "vitest";
import {
  formatDuration,
  formatRate,
  formatCount,
  csvNumber,
  csvDecimal,
} from "@/lib/number-format";

test.each([
  [1724.9999999999998, "1,725 ms"],
  [880.0000000000001, "880 ms"],
  [24200.000000000004, "24.2 s"],
  [50599.99999999999, "50.6 s"],
  [9999, "9,999 ms"],
  [10000, "10.0 s"],
  [0, "0 ms"],
])("duration %s is readable", (value, expected) => expect(formatDuration(value)).toBe(expected));
test("rates stay fractions at input and display as percentages", () => {
  expect(formatRate(0.3333333333333333)).toBe("33.3%");
  expect(formatRate("0.3333333333333333")).toBe("33.3%");
  expect(formatRate(0)).toBe("0.0%");
  expect(formatCount(1234567)).toBe("1,234,567");
});
test.each([null, undefined, NaN, Infinity, "", "bad"])("unknown %s stays unknown", (value) => {
  expect(formatDuration(value)).toBe("Unknown");
  expect(formatRate(value)).toBe("Unknown");
  expect(formatCount(value)).toBe("Unknown");
});
test.each([
  [1724.9999999999998, "1725"],
  [880.0000000000001, "880"],
  [24200.000000000004, "24200"],
  [50599.99999999999, "50600"],
  [0.3333333333333333, "0.333"],
  [1234.56789, "1234.568"],
])("CSV %s rounds to three decimal places without grouping", (value, expected) => {
  expect(csvNumber(value)).toBe(expected);
  expect(csvCell(value)).toBe(`"${expected}"`);
});
test("CSV money rounds exact decimal strings to three places", () => {
  expect(csvDecimal("1234567890123.4565")).toBe("1234567890123.457");
  expect(csvDecimal("0.000000000001")).toBe("0.000");
  expect(csvDecimal(null)).toBe("");
});
