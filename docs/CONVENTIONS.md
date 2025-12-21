# Project Conventions

Quick reference for AI and developers. Follow these patterns strictly.

## Stack

- **Frontend:** React 18, TypeScript, Vite, Tailwind CSS v4, shadcn/ui
- **Backend:** Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2
- **Database:** PostgreSQL 15+, ChromaDB (vectors), Redis (cache)
- **State:** React Query (server), React Context (auth only), React Hook Form (forms)

---

## Tailwind CSS v4 (Critical)

### Setup

```css
/* src/index.css */
@import "tailwindcss";

@theme {
  --color-brand-500: oklch(0.55 0.2 250);
  --font-sans: "Inter", sans-serif;
}
```

### v4 Syntax (Use This)

| Pattern           | v3 (WRONG)           | v4 (CORRECT)                |
| ----------------- | -------------------- | --------------------------- |
| Config            | `tailwind.config.js` | `@theme { }` in CSS         |
| Import            | `@tailwind base`     | `@import "tailwindcss"`     |
| Gradients         | `bg-gradient-to-r`   | `bg-linear-to-r`            |
| Colors            | `#3b82f6`            | `oklch(0.62 0.21 255)`      |
| Container queries | Plugin               | Native `@container`, `@sm:` |
| Arbitrary         | `grid-cols-[13]`     | `grid-cols-13`              |

### v4 Features to Use

```html
@container + @sm:grid-cols-2
<!-- Container queries -->
not-hover:opacity-75
<!-- Negation -->
bg-linear-45
<!-- Angle gradients -->
inset-shadow-sm
<!-- Shadow stacking -->
data-[state=active]:bg-blue
<!-- Data attributes -->
```

---

## FastAPI Conventions

### Naming

| Element     | Pattern                     | Example                        |
| ----------- | --------------------------- | ------------------------------ |
| Function    | `{verb}_{resource}`         | `list_jobs`, `create_document` |
| Request     | `{Action}{Resource}Request` | `CreateJobRequest`             |
| Response    | `{Resource}Response`        | `JobResponse`                  |
| Path param  | `{resource}_id`             | `/jobs/{job_id}`               |
| Query param | snake_case                  | `per_page`, `sort_by`          |

### Enums (StrEnum)

```python
from enum import StrEnum

class DocumentStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
```

### Endpoint Template

```python
@router.get("", response_model=PaginatedResponse[JobResponse])
async def list_jobs(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
) -> PaginatedResponse[JobResponse]:
    ...

@router.post("", response_model=JobResponse, status_code=201)
async def create_job(request: CreateJobRequest) -> JobResponse:
    ...
```

### Tags (SDK Grouping)

One tag per endpoint. Maps to SDK service:

- `auth` → `authService`
- `documents` → `documentsService`
- `search` → `searchService`
- `jobs` → `jobsService`
- `applications` → `applicationsService`

---

## React Component Patterns

### Rule 1: Composition Over Props

```tsx
// ❌ NEVER: Boolean props controlling render
<Card isCompact showActions hideHeader isEditing />

// ✅ ALWAYS: Compose what you need
<Card.Root>
  <Card.Header />
  <Card.Content />
  <Card.Actions />
</Card.Root>
```

### Rule 2: Lift Provider for Sibling Access

```tsx
// ❌ State trapped in component
<Page>
  <SearchForm />        {/* Has state */}
  <ExportButton />      {/* Can't access it */}
</Page>

// ✅ Provider lifted up
<SearchProvider>
  <Page>
    <SearchForm />
    <ExportButton />    {/* Uses context */}
  </Page>
</SearchProvider>
```

### Rule 3: JSX Over Config Arrays

```tsx
// ❌ Config array with conditions
const actions = [
  { id: "edit", show: canEdit },
  { id: "delete", show: canDelete },
];

// ✅ Just render JSX
<>
  {canEdit && <EditButton />}
  {canDelete && <DeleteButton />}
</>;
```

### Rule 4: Distinct Components Over Modes

```tsx
// ❌ One component with mode flags
<UserForm isEditing isQuickEdit hideTerms />

// ✅ Separate components sharing internals
<CreateUserForm />
<EditUserForm />
<QuickEditUserForm />
```

---

## shadcn Component Structure

```
components/
├── ui/              # shadcn (don't modify)
├── custom/          # Custom following shadcn patterns
└── features/        # Feature-specific with providers
    ├── jobs/
    │   ├── job-form-provider.tsx
    │   ├── job-form.tsx
    │   └── job-card.tsx
    └── search/
        ├── search-provider.tsx
        └── search-input.tsx
```

### Custom Component Template

```tsx
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const variants = cva("base-classes", {
  variants: {
    variant: { default: "...", destructive: "..." },
    size: { sm: "...", md: "...", lg: "..." },
  },
  defaultVariants: { variant: "default", size: "md" },
});

interface Props extends VariantProps<typeof variants> {
  className?: string;
}

const Component = React.forwardRef<HTMLDivElement, Props>(
  ({ className, variant, size, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(variants({ variant, size }), className)}
      {...props}
    />
  )
);
Component.displayName = "Component";

export { Component, variants as componentVariants };
```

---

## File Naming

| Type       | Convention      | Example               |
| ---------- | --------------- | --------------------- |
| Components | kebab-case      | `document-card.tsx`   |
| Hooks      | camelCase + use | `useDocuments.ts`     |
| Providers  | kebab-case      | `search-provider.tsx` |
| Utils      | kebab-case      | `format-date.ts`      |

---

## Import Order

```tsx
// 1. React
import * as React from "react";
// 2. External libs
import { useQuery } from "@tanstack/react-query";
// 3. API/Generated
import { jobsListJobs } from "@/api/generated";
// 4. Components
import { Button } from "@/components/ui/button";
// 5. Hooks/Utils
import { cn } from "@/lib/utils";
// 6. Types
import type { Job } from "@/api/generated";
```

---

## API Client (Hey API)

```typescript
// Auto-generated, type-safe
const { data } = await jobsListJobs({ query: { page: 1 } });
const job = await jobsCreateJob({ body: { title: "..." } });

// With React Query
const { data } = useQuery({
  queryKey: ["jobs", page],
  queryFn: () => jobsListJobs({ query: { page } }),
});
```

---

## Quick Rules

1. **No boolean render props** - Use composition
2. **No config arrays for UI** - Use JSX
3. **One tag per endpoint** - For SDK grouping
4. **StrEnum for enums** - Not `(str, Enum)`
5. **Lift providers up** - For sibling access
6. **v4 gradient syntax** - `bg-linear-*` not `bg-gradient-*`
7. **forwardRef all components** - For ref support
8. **cva for variants** - Not manual conditionals
9. **Field() with description** - For OpenAPI docs
10. **snake_case API, camelCase UI** - Consistent naming
