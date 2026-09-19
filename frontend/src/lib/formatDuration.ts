function formatPositiveDuration(durationMs: number) {
  const totalSeconds = durationMs / 1000;
  if (totalSeconds < 0.1) return "<0.1 s";
  if (totalSeconds < 10) return `${totalSeconds.toFixed(1)} s`;

  const roundedSeconds = Math.round(totalSeconds);
  if (roundedSeconds < 60) return `${roundedSeconds} s`;

  const totalMinutes = Math.floor(roundedSeconds / 60);
  const remainingSeconds = roundedSeconds % 60;
  if (totalMinutes < 60) {
    return remainingSeconds ? `${totalMinutes} min ${remainingSeconds} s` : `${totalMinutes} min`;
  }

  const totalHours = Math.floor(totalMinutes / 60);
  const remainingMinutes = totalMinutes % 60;
  return remainingMinutes ? `${totalHours} hr ${remainingMinutes} min` : `${totalHours} hr`;
}

export function formatDuration(durationMs?: number | null) {
  if (typeof durationMs !== "number" || !Number.isFinite(durationMs) || durationMs <= 0) return "—";
  return formatPositiveDuration(durationMs);
}

export function formatElapsedDuration(durationMs?: number | null) {
  if (typeof durationMs !== "number" || !Number.isFinite(durationMs) || durationMs <= 0) return "0 s";
  return formatPositiveDuration(durationMs);
}