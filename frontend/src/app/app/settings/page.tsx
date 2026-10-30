"use client";

import { useSyncExternalStore } from "react";
import { applyTheme, readTheme, subscribeTheme, type ThemeChoice } from "@/lib/theme";

export default function SettingsPage() {
  const theme = useSyncExternalStore<ThemeChoice>(subscribeTheme, readTheme, () => "system");
  const choose = applyTheme;

  return (
    <section className="max-w-xl space-y-4">
      <h1 className="text-2xl font-semibold">Settings</h1>
      <fieldset className="panel space-y-2 p-4">
        <legend className="px-1 font-semibold">Theme</legend>
        {(["system", "light", "dark"] as const).map((choice) => (
          <label key={choice} className="flex items-center gap-2 text-sm" htmlFor={`theme-${choice}`}>
            <input id={`theme-${choice}`} type="radio" name="theme" checked={theme === choice} onChange={() => choose(choice)} />
            {choice === "system" ? "System (follow the device)" : choice === "light" ? "Light" : "Dark"}
          </label>
        ))}
      </fieldset>
    </section>
  );
}
