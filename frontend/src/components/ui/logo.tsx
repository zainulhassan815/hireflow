import type { SVGProps } from "react";

import { cn } from "@/lib/utils";

export function Logo({ className, ...props }: SVGProps<SVGSVGElement>) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 32 32"
      role="img"
      aria-label="Hireflow"
      className={cn("size-full", className)}
      {...props}
    >
      <title>Hireflow</title>
      <rect x="4" y="20" width="5" height="8" rx="1.2" fill="#f59e0b" />
      <rect x="11" y="16" width="5" height="12" rx="1.2" fill="#ec4899" />
      <rect x="18" y="11" width="5" height="17" rx="1.2" fill="#8b5cf6" />
      <rect
        x="25"
        y="6"
        width="5"
        height="22"
        rx="1.2"
        fill="#1d4ed8"
        transform="rotate(4 27.5 17)"
      />
    </svg>
  );
}
