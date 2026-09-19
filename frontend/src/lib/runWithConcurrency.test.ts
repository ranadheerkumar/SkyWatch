import { describe, expect, it } from "vitest";
import { getConcurrencyLimit, runWithConcurrency } from "./runWithConcurrency";

describe("runWithConcurrency", () => {
  it("processes every item without exceeding the requested worker limit", async () => {
    const items = Array.from({ length: 9 }, (_, index) => index + 1);
    const completed: number[] = [];
    let activeWorkers = 0;
    let maximumActiveWorkers = 0;

    await runWithConcurrency(items, 3, async (item) => {
      activeWorkers += 1;
      maximumActiveWorkers = Math.max(maximumActiveWorkers, activeWorkers);
      await new Promise((resolve) => setTimeout(resolve, 5));
      completed.push(item);
      activeWorkers -= 1;
    });

    expect(maximumActiveWorkers).toBe(3);
    expect(completed.sort((left, right) => left - right)).toEqual(items);
  });

  it("clamps worker counts to the available items and safe bounds", () => {
    expect(getConcurrencyLimit(0, 4)).toBe(1);
    expect(getConcurrencyLimit(20, 2)).toBe(2);
    expect(getConcurrencyLimit(3, 0)).toBe(0);
    expect(getConcurrencyLimit(Number.NaN, 4)).toBe(1);
  });
});
