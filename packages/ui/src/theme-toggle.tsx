"use client";

import { useEffect, useState } from "react";

import { Button } from "./button";

type Theme = "light" | "dark";

const STORAGE_KEY = "argus-theme";

function applyTheme(theme: Theme): void {
  document.documentElement.classList.toggle("dark", theme === "dark");
  document.documentElement.dataset.theme = theme;
}

function readStoredTheme(): Theme {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    return stored === "light" ? "light" : "dark";
  } catch {
    // Storage can be unavailable (private mode, sandboxed iframe).
    return "dark";
  }
}

function persistTheme(theme: Theme): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    // Preference simply will not survive the session.
  }
}

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>("dark");

  useEffect(() => {
    const initial = readStoredTheme();
    setTheme(initial);
    applyTheme(initial);
  }, []);

  function toggle() {
    const next: Theme = theme === "dark" ? "light" : "dark";
    setTheme(next);
    applyTheme(next);
    persistTheme(next);
  }

  return (
    <Button variant="ghost" size="sm" onClick={toggle} aria-label="Toggle color theme">
      {theme === "dark" ? "Light" : "Dark"}
    </Button>
  );
}
