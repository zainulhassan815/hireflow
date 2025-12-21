# Frontend Standards - HR Screening RAG System

This document defines frontend standards including Tailwind CSS v4 patterns and shadcn/ui component conventions.

## Tech Stack

| Technology      | Version | Purpose           |
| --------------- | ------- | ----------------- |
| React           | 18.x    | UI Framework      |
| TypeScript      | 5.x     | Type Safety       |
| Vite            | 5.x     | Build Tool        |
| Tailwind CSS    | 4.x     | Styling           |
| shadcn/ui       | Latest  | Component Library |
| React Query     | 5.x     | Server State      |
| React Hook Form | 7.x     | Form Handling     |
| React Router    | 6.x     | Routing           |

---

## Tailwind CSS v4 Setup

### Installation (Vite)

```bash
npm install tailwindcss @tailwindcss/vite
```

### Vite Configuration

```typescript
// vite.config.ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
});
```

### CSS Entry Point

```css
/* src/index.css */
@import "tailwindcss";

/* Theme customization */
@theme {
  /* Colors - using oklch for wider gamut */
  --color-primary: oklch(0.55 0.2 250);
  --color-primary-foreground: oklch(0.98 0 0);

  /* Custom brand colors */
  --color-brand-50: oklch(0.97 0.01 250);
  --color-brand-100: oklch(0.93 0.02 250);
  --color-brand-500: oklch(0.55 0.2 250);
  --color-brand-600: oklch(0.48 0.2 250);
  --color-brand-700: oklch(0.42 0.18 250);

  /* Semantic colors */
  --color-success: oklch(0.72 0.19 145);
  --color-warning: oklch(0.8 0.15 85);
  --color-error: oklch(0.63 0.24 25);

  /* Typography */
  --font-sans: "Inter", ui-sans-serif, system-ui, sans-serif;
  --font-mono: "JetBrains Mono", ui-monospace, monospace;

  /* Custom breakpoint */
  --breakpoint-3xl: 1920px;

  /* Custom animations */
  --ease-spring: cubic-bezier(0.34, 1.56, 0.64, 1);
  --ease-smooth: cubic-bezier(0.4, 0, 0.2, 1);

  /* Spacing (base is 0.25rem = 4px) */
  --spacing: 0.25rem;
}

/* Dark mode theme overrides */
@theme dark {
  --color-primary: oklch(0.7 0.18 250);
  --color-primary-foreground: oklch(0.1 0 0);
}
```

---

## Tailwind v4 Key Differences (Avoid v3 Patterns!)

### Configuration

```css
/* ❌ v3: JavaScript config file */
/* tailwind.config.js - NO LONGER NEEDED */

/* ✅ v4: CSS-first configuration */
@import "tailwindcss";

@theme {
  --color-brand: oklch(0.55 0.2 250);
  --font-display: "Satoshi", sans-serif;
}
```

### Content Detection

```css
/* ❌ v3: Manual content paths */
/* content: ['./src/**/*.{js,ts,jsx,tsx}'] */

/* ✅ v4: Automatic detection */
/* No configuration needed - respects .gitignore */

/* For external packages, use @source */
@source "../node_modules/@company/ui-lib";
```

### Gradient Classes

```html
<!-- ❌ v3: Old gradient syntax -->
<div class="bg-gradient-to-r from-blue-500 to-purple-500"></div>

<!-- ✅ v4: New gradient syntax -->
<div class="bg-linear-to-r from-blue-500 to-purple-500"></div>

<!-- ✅ v4: Angle-based gradients -->
<div class="bg-linear-45 from-blue-500 to-purple-500"></div>

<!-- ✅ v4: Color interpolation -->
<div class="bg-linear-to-r/oklch from-blue-500 to-purple-500"></div>
```

### Container Queries (Built-in)

```html
<!-- ❌ v3: Required plugin @tailwindcss/container-queries -->

<!-- ✅ v4: Native support -->
<div class="@container">
  <div class="grid grid-cols-1 @sm:grid-cols-2 @lg:grid-cols-4">
    <!-- Content -->
  </div>
</div>
```

### Dynamic Values

```html
<!-- ❌ v3: Arbitrary values needed -->
<div class="grid-cols-[13]"></div>
<div class="mt-[17]"></div>

<!-- ✅ v4: Direct support for any number -->
<div class="grid-cols-13"></div>
<div class="mt-17"></div>
```

### Data Attributes

```html
<!-- ❌ v3: Required configuration -->
<!-- data: { current: 'data-current' } in config -->

<!-- ✅ v4: Zero configuration -->
<div data-state="active" class="data-[state=active]:bg-blue-500"></div>
<div data-current class="data-current:opacity-100"></div>
```

### New Variants

```html
<!-- ✅ v4: not-* variant -->
<div class="not-hover:opacity-75 hover:opacity-100"></div>
<div class="not-disabled:cursor-pointer"></div>

<!-- ✅ v4: in-* variant (implicit groups) -->
<div class="group">
  <span class="in-[.group:hover]:text-blue-500"></span>
</div>

<!-- ✅ v4: nth-* variants -->
<li class="nth-[2n]:bg-gray-100"></li>
<li class="nth-last-3:font-bold"></li>

<!-- ✅ v4: inert variant -->
<div class="inert:opacity-50 inert:pointer-events-none"></div>
```

### 3D Transforms

```html
<!-- ✅ v4: Native 3D transform support -->
<div class="perspective-dramatic">
  <div class="rotate-x-12 rotate-y-6 transform-3d">
    <!-- 3D transformed content -->
  </div>
</div>
```

### Shadow Stacking

```html
<!-- ✅ v4: Stack multiple shadows -->
<div class="shadow-md inset-shadow-sm inset-ring-1 ring-black/5">
  <!-- Up to 4 shadow layers -->
</div>
```

### Color System (oklch)

```css
/* ❌ v3: RGB-based colors */
--color-blue-500: #3b82f6;

/* ✅ v4: oklch for wider gamut */
--color-blue-500: oklch(0.62 0.21 255);
```

---

## shadcn/ui Standards

### Installation

```bash
npx shadcn@latest init
```

Select options:

- Style: Default
- Base color: Slate
- CSS variables: Yes
- Tailwind CSS v4: Yes (if prompted)

### Component Structure

```
src/
├── components/
│   ├── ui/                 # shadcn components (don't modify)
│   │   ├── button.tsx
│   │   ├── card.tsx
│   │   ├── dialog.tsx
│   │   └── ...
│   ├── custom/             # Custom components following shadcn patterns
│   │   ├── match-score-badge.tsx
│   │   ├── document-card.tsx
│   │   └── candidate-row.tsx
│   ├── layout/             # Layout components
│   │   ├── sidebar.tsx
│   │   ├── header.tsx
│   │   └── page-container.tsx
│   └── features/           # Feature-specific compound components
│       ├── jobs/
│       ├── documents/
│       └── candidates/
```

### Custom Component Pattern (shadcn-style)

Follow shadcn conventions for custom components:

```typescript
// src/components/custom/match-score-badge.tsx
import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const matchScoreBadgeVariants = cva(
  // Base styles
  "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium transition-colors",
  {
    variants: {
      score: {
        high: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
        medium:
          "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400",
        low: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
      },
      size: {
        sm: "px-2 py-0.5 text-xs",
        md: "px-2.5 py-0.5 text-sm",
        lg: "px-3 py-1 text-sm",
      },
    },
    defaultVariants: {
      score: "medium",
      size: "md",
    },
  }
);

function getScoreLevel(score: number): "high" | "medium" | "low" {
  if (score >= 0.8) return "high";
  if (score >= 0.5) return "medium";
  return "low";
}

export interface MatchScoreBadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    Omit<VariantProps<typeof matchScoreBadgeVariants>, "score"> {
  score: number; // 0-1
  showPercentage?: boolean;
}

const MatchScoreBadge = React.forwardRef<HTMLSpanElement, MatchScoreBadgeProps>(
  ({ className, score, size, showPercentage = true, ...props }, ref) => {
    const scoreLevel = getScoreLevel(score);
    const percentage = Math.round(score * 100);

    return (
      <span
        ref={ref}
        className={cn(
          matchScoreBadgeVariants({ score: scoreLevel, size }),
          className
        )}
        {...props}
      >
        <svg
          className="size-3"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
        >
          {scoreLevel === "high" && (
            <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
          )}
          {scoreLevel === "high" && <polyline points="22 4 12 14.01 9 11.01" />}
          {scoreLevel === "medium" && <circle cx="12" cy="12" r="10" />}
          {scoreLevel === "low" && (
            <>
              <circle cx="12" cy="12" r="10" />
              <line x1="15" y1="9" x2="9" y2="15" />
              <line x1="9" y1="9" x2="15" y2="15" />
            </>
          )}
        </svg>
        {showPercentage && <span>{percentage}%</span>}
      </span>
    );
  }
);

MatchScoreBadge.displayName = "MatchScoreBadge";

export { MatchScoreBadge, matchScoreBadgeVariants };
```

### Document Card Component

```typescript
// src/components/custom/document-card.tsx
import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  FileText,
  FileImage,
  File,
  Loader2,
  CheckCircle,
  XCircle,
} from "lucide-react";
import type {
  DocumentResponse,
  DocumentStatus,
  DocumentType,
} from "@/api/generated";

const documentCardVariants = cva(
  "group cursor-pointer transition-all hover:shadow-md",
  {
    variants: {
      status: {
        pending:
          "border-yellow-200 bg-yellow-50/50 dark:border-yellow-900 dark:bg-yellow-950/20",
        processing:
          "border-blue-200 bg-blue-50/50 dark:border-blue-900 dark:bg-blue-950/20",
        completed: "border-border bg-card",
        failed:
          "border-red-200 bg-red-50/50 dark:border-red-900 dark:bg-red-950/20",
      },
    },
    defaultVariants: {
      status: "completed",
    },
  }
);

const statusIcons: Record<DocumentStatus, React.ReactNode> = {
  pending: <Loader2 className="size-4 animate-spin text-yellow-500" />,
  processing: <Loader2 className="size-4 animate-spin text-blue-500" />,
  completed: <CheckCircle className="size-4 text-green-500" />,
  failed: <XCircle className="size-4 text-red-500" />,
};

const typeIcons: Record<DocumentType, React.ReactNode> = {
  resume: <FileText className="size-8 text-blue-500" />,
  report: <FileText className="size-8 text-purple-500" />,
  contract: <FileText className="size-8 text-orange-500" />,
  letter: <FileText className="size-8 text-green-500" />,
  other: <File className="size-8 text-gray-500" />,
};

export interface DocumentCardProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof documentCardVariants> {
  document: DocumentResponse;
  onView?: (id: string) => void;
  onDelete?: (id: string) => void;
}

const DocumentCard = React.forwardRef<HTMLDivElement, DocumentCardProps>(
  ({ className, document, status, onView, onDelete, ...props }, ref) => {
    const {
      id,
      filename,
      doc_type,
      file_size,
      created_at,
      status: docStatus,
    } = document;

    const formatFileSize = (bytes: number) => {
      if (bytes < 1024) return `${bytes} B`;
      if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
      return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    };

    const formatDate = (date: Date) => {
      return new Intl.DateTimeFormat("en-US", {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      }).format(date);
    };

    return (
      <Card
        ref={ref}
        className={cn(documentCardVariants({ status: docStatus }), className)}
        onClick={() => onView?.(id)}
        {...props}
      >
        <CardHeader className="flex flex-row items-start gap-3 p-4">
          <div className="rounded-lg bg-muted p-2">
            {typeIcons[doc_type ?? "other"]}
          </div>
          <div className="flex-1 space-y-1 overflow-hidden">
            <p className="truncate font-medium leading-none">{filename}</p>
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <span>{formatFileSize(file_size)}</span>
              <span>•</span>
              <span>{formatDate(created_at)}</span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {statusIcons[docStatus]}
            {doc_type && (
              <Badge variant="secondary" className="capitalize">
                {doc_type}
              </Badge>
            )}
          </div>
        </CardHeader>
      </Card>
    );
  }
);

DocumentCard.displayName = "DocumentCard";

export { DocumentCard, documentCardVariants };
```

### Utility Functions

```typescript
// src/lib/utils.ts
import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatDate(date: Date | string) {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(date));
}

export function formatDateTime(date: Date | string) {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(date));
}

export function formatFileSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatPercentage(value: number) {
  return `${Math.round(value * 100)}%`;
}
```

---

## Component Guidelines

### 1. Use `forwardRef` for All Components

```typescript
// ✅ Good: Supports ref forwarding
const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, ...props }, ref) => (
    <button ref={ref} className={cn("...", className)} {...props} />
  )
);
Button.displayName = "Button";

// ❌ Bad: No ref support
const Button = ({ className, ...props }: ButtonProps) => (
  <button className={cn("...", className)} {...props} />
);
```

### 2. Use `cva` for Variants

```typescript
// ✅ Good: Type-safe variants with cva
import { cva, type VariantProps } from "class-variance-authority";

const buttonVariants = cva("base-classes", {
  variants: {
    variant: { default: "...", destructive: "..." },
    size: { sm: "...", md: "...", lg: "..." },
  },
  defaultVariants: {
    variant: "default",
    size: "md",
  },
});

interface ButtonProps extends VariantProps<typeof buttonVariants> {}

// ❌ Bad: Manual className conditionals
const getButtonClass = (variant: string, size: string) => {
  let classes = "base";
  if (variant === "default") classes += " default-classes";
  // ...messy
};
```

### 3. Spread Props Last

```typescript
// ✅ Good: className and other overrides work
<button
  ref={ref}
  className={cn(buttonVariants({ variant, size }), className)}
  {...props}
/>

// ❌ Bad: Props override className
<button {...props} className={cn(buttonVariants({ variant, size }), className)} />
```

### 4. Export Variants for Composition

```typescript
// ✅ Good: Export both component and variants
export { Button, buttonVariants };

// Usage in other components
import { buttonVariants } from "@/components/ui/button";

<Link className={buttonVariants({ variant: "outline" })}>
  Link styled as button
</Link>;
```

---

## File Naming Conventions

| Type       | Convention                  | Example             |
| ---------- | --------------------------- | ------------------- |
| Components | kebab-case                  | `document-card.tsx` |
| Hooks      | camelCase with `use` prefix | `useDocuments.ts`   |
| Utils      | kebab-case                  | `format-date.ts`    |
| Types      | kebab-case                  | `api-types.ts`      |
| Pages      | kebab-case                  | `job-details.tsx`   |

---

## Import Order

```typescript
// 1. React
import * as React from "react";
import { useState, useEffect } from "react";

// 2. External libraries
import { useQuery } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";

// 3. Internal - API/Generated
import { documentsListDocuments } from "@/api/generated";
import type { DocumentResponse } from "@/api/generated";

// 4. Internal - Components
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { DocumentCard } from "@/components/custom/document-card";

// 5. Internal - Hooks
import { useDocuments } from "@/hooks/use-documents";

// 6. Internal - Utils/Lib
import { cn, formatDate } from "@/lib/utils";

// 7. Types (type-only imports)
import type { DocumentCardProps } from "@/components/custom/document-card";
```

---

## Common Patterns

### Loading States

```typescript
// Use skeleton from shadcn
import { Skeleton } from "@/components/ui/skeleton";

function DocumentListSkeleton() {
  return (
    <div className="space-y-3">
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} className="flex items-center gap-3 rounded-lg border p-4">
          <Skeleton className="size-12 rounded-lg" />
          <div className="flex-1 space-y-2">
            <Skeleton className="h-4 w-48" />
            <Skeleton className="h-3 w-24" />
          </div>
        </div>
      ))}
    </div>
  );
}
```

### Empty States

```typescript
import { FileX } from "lucide-react";
import { Button } from "@/components/ui/button";

function EmptyState({
  icon: Icon = FileX,
  title,
  description,
  action,
}: {
  icon?: React.ComponentType<{ className?: string }>;
  title: string;
  description: string;
  action?: { label: string; onClick: () => void };
}) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-center">
      <div className="rounded-full bg-muted p-4">
        <Icon className="size-8 text-muted-foreground" />
      </div>
      <h3 className="mt-4 text-lg font-semibold">{title}</h3>
      <p className="mt-1 text-sm text-muted-foreground">{description}</p>
      {action && (
        <Button className="mt-4" onClick={action.onClick}>
          {action.label}
        </Button>
      )}
    </div>
  );
}
```

### Error States

```typescript
import { AlertCircle } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

function ErrorState({
  title = "Something went wrong",
  message,
  retry,
}: {
  title?: string;
  message: string;
  retry?: () => void;
}) {
  return (
    <Alert variant="destructive">
      <AlertCircle className="size-4" />
      <AlertTitle>{title}</AlertTitle>
      <AlertDescription className="flex items-center justify-between">
        <span>{message}</span>
        {retry && (
          <Button variant="outline" size="sm" onClick={retry}>
            Try again
          </Button>
        )}
      </AlertDescription>
    </Alert>
  );
}
```

---

## Package Versions

```json
{
  "dependencies": {
    "react": "^18.3.0",
    "react-dom": "^18.3.0",
    "react-router-dom": "^6.28.0",
    "@tanstack/react-query": "^5.60.0",
    "react-hook-form": "^7.53.0",
    "@hookform/resolvers": "^3.9.0",
    "zod": "^3.23.0",
    "class-variance-authority": "^0.7.0",
    "clsx": "^2.1.0",
    "tailwind-merge": "^2.5.0",
    "lucide-react": "^0.460.0"
  },
  "devDependencies": {
    "typescript": "^5.6.0",
    "vite": "^5.4.0",
    "tailwindcss": "^4.0.0",
    "@tailwindcss/vite": "^4.0.0",
    "@hey-api/openapi-ts": "^0.54.0",
    "@hey-api/client-fetch": "^0.4.0"
  }
}
```

---

## References

- [Tailwind CSS v4 Documentation](https://tailwindcss.com/docs)
- [Tailwind CSS v4 Blog Post](https://tailwindcss.com/blog/tailwindcss-v4)
- [shadcn/ui Documentation](https://ui.shadcn.com)
- [Class Variance Authority](https://cva.style/docs)
- [TanStack Query](https://tanstack.com/query/latest)
