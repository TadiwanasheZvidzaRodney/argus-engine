import type { HTMLAttributes, ReactNode } from "react";

import { cn } from "./cn";

export interface CardProps extends Omit<HTMLAttributes<HTMLDivElement>, "title"> {
  title?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
}

export function Card({ title, description, actions, className, children, ...props }: CardProps) {
  return (
    <section
      className={cn("rounded-lg border border-border bg-surface shadow-sm", className)}
      {...props}
    >
      {(title ?? actions) && (
        <header className="flex items-start justify-between gap-4 border-b border-border px-4 py-3">
          <div>
            {title && <h2 className="text-sm font-semibold text-foreground">{title}</h2>}
            {description && <p className="mt-1 text-xs text-muted-foreground">{description}</p>}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className="px-4 py-3">{children}</div>
    </section>
  );
}
