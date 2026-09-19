"use client";

import { useEffect, useRef, useState } from "react";

export function useToast(durationMs = 2400) {
  const [message, setMessage] = useState("");
  const timerRef = useRef<number | undefined>(undefined);

  useEffect(() => () => {
    if (timerRef.current !== undefined) window.clearTimeout(timerRef.current);
  }, []);

  const notify = (nextMessage: string) => {
    setMessage(nextMessage);
    if (timerRef.current !== undefined) window.clearTimeout(timerRef.current);
    timerRef.current = window.setTimeout(() => {
      setMessage("");
      timerRef.current = undefined;
    }, durationMs);
  };

  const clearToast = () => {
    if (timerRef.current !== undefined) window.clearTimeout(timerRef.current);
    timerRef.current = undefined;
    setMessage("");
  };

  return { toast: message, notify, clearToast };
}
