# Frontend API Integration Rules

Strict rules for wiring frontend pages to the backend. No exceptions.

---

## 1. Types come from the SDK only

```tsx
// ✅ Always import from @/api
import { type DocumentResponse, type SearchResponse } from "@/api";

// ❌ Never define custom types that duplicate the SDK
interface Document {
  id: string;       // WRONG — use DocumentResponse from SDK
  filename: string;
}
```

**Why:** The SDK types are generated from the OpenAPI spec. Custom types
drift, break, and lie. One source of truth.

---

## 2. API calls use SDK functions only

```tsx
// ✅ Use generated SDK functions
import { documentsListDocuments, documentsUploadDocument } from "@/api";

const { data, error } = await documentsListDocuments();

// ❌ Never use raw fetch
const res = await fetch("/api/documents");

// ❌ Never use the client directly
import { client } from "@/api/generated/client.gen";
client.get({ url: "/api/documents" });
```

**Why:** SDK functions are typed end-to-end (request → response → error).
Raw fetch loses all type safety.

---

## 3. No mock data in pages

```tsx
// ✅ Fetch from API, show loading/empty/error states
const [docs, setDocs] = useState<DocumentResponse[]>([]);
const [loading, setLoading] = useState(true);

useEffect(() => {
  documentsListDocuments().then(({ data }) => {
    setDocs(data ?? []);
    setLoading(false);
  });
}, []);

// ❌ Never hardcode mock arrays
const mockDocuments = [
  { id: "1", filename: "resume.pdf", ... },
];
```

---

## 4. Error handling pattern

```tsx
import { toast } from "sonner";

const { data, error } = await someApiCall({ body: ... });
if (error) {
  const message =
    typeof error === "object" && "detail" in error
      ? (error as { detail: string }).detail
      : "Something went wrong";
  toast.error(message);
  return;
}
// use data
```

Backend errors always return `{"detail": "..."}`. Extract and toast.

---

## 5. Loading and empty states are mandatory

Every page that fetches data must handle three states:

| State | What to show |
|-------|-------------|
| Loading | Skeleton or spinner |
| Empty | Descriptive empty state with action (e.g. "No documents yet. Upload one.") |
| Error | Toast + inline message with retry option |

---

## 6. File uploads use FormData via SDK

```tsx
const { data, error } = await documentsUploadDocument({
  body: { file },  // UploadFile handled by SDK
});
```

---

## 7. No `any` types

```tsx
// ✅ Use the SDK type
const docs: DocumentResponse[] = data ?? [];

// ❌ Never
const docs: any[] = data;
```

---

## 8. Date formatting uses shared utils

```tsx
import { formatDate, formatDateTime, formatFileSize } from "@/lib/utils";

// ✅ Consistent formatting across the app
<span>{formatDateTime(doc.created_at)}</span>
<span>{formatFileSize(doc.size_bytes)}</span>
```

---

## 9. Auth state comes from useAuth() only

```tsx
import { useAuth } from "@/providers/use-auth";

const { user } = useAuth();
// user is typed as UserResponse | null
```

Never read tokens directly from localStorage in components.

---

## 10. SDK re-export via @/api barrel

All imports go through the barrel:

```tsx
import {
  documentsListDocuments,
  searchSearchDocuments,
  type DocumentResponse,
  type SearchResponse,
} from "@/api";
```

Never import from `@/api/generated/sdk.gen` or `@/api/generated/types.gen` directly.
