"use client";

import { useEffect } from "react";

/** Pages restored from the back/forward cache could show a stale signed-in view: reload them. */
export function BfcacheReload() {
  useEffect(() => {
    const onShow = (e: PageTransitionEvent) => {
      if (e.persisted) window.location.reload();
    };
    window.addEventListener("pageshow", onShow);
    return () => window.removeEventListener("pageshow", onShow);
  }, []);
  return null;
}
