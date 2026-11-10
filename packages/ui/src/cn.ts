export type ClassValue = string | false | null | undefined;

/** Minimal class-name joiner; keeps the package dependency-free. */
export function cn(...values: ClassValue[]): string {
  return values.filter(Boolean).join(" ");
}
