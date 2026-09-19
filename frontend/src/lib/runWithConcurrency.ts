export function getConcurrencyLimit(requestedConcurrency: number, itemCount: number, maximumConcurrency = 5): number {
  if (itemCount <= 0) return 0;
  const requested = Number.isFinite(requestedConcurrency) ? Math.floor(requestedConcurrency) : 1;
  const maximum = Math.max(1, Math.floor(maximumConcurrency) || 1);
  return Math.min(itemCount, Math.max(1, Math.min(maximum, requested)));
}

export async function runWithConcurrency<T>(
  items: readonly T[],
  requestedConcurrency: number,
  worker: (item: T, index: number) => Promise<void>,
): Promise<void> {
  const workerCount = getConcurrencyLimit(requestedConcurrency, items.length);
  let nextIndex = 0;

  const runWorker = async () => {
    while (true) {
      const index = nextIndex;
      nextIndex += 1;
      if (index >= items.length) return;
      await worker(items[index], index);
    }
  };

  await Promise.all(Array.from({ length: workerCount }, runWorker));
}
