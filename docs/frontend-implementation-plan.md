# Frontend Implementation Plan

## SRS Document Alignment

This document outlines the implementation plan to align the frontend with the SRS Document requirements (FR01-FR20, UC-01 to UC-12).

**Focus:** Frontend implementation for architecture presentation
**Approach:** Mock data (no backend integration yet)

---

## Current State

### Existing Pages
| Page | Description | Status |
|------|-------------|--------|
| Dashboard | Stats, recent applications | Exists |
| Jobs | Job cards with mock data | Exists |
| Candidates | Table with filters | Exists |
| Analytics | AI search demo | To be renamed |
| Settings | Profile, notifications | Exists |

### Existing Infrastructure
- React Router 7.11 with nested routes
- Auth provider (skeleton)
- OpenAPI-TS configured for API client
- shadcn/ui + Base UI components
- Tailwind CSS v4 with theming
- Sonner for toast notifications

---

## Implementation Phases

### Phase 1: Authentication

**Use Cases:** UC-01 (Login), UC-02 (Reset Password)
**Requirements:** FR01, FR02, FR03

#### New Files
| File | Description |
|------|-------------|
| `src/pages/auth/login.tsx` | Login page with email/password form |
| `src/pages/auth/register.tsx` | Registration page (email, password, name) |
| `src/pages/auth/forgot-password.tsx` | Request password reset form |
| `src/pages/auth/reset-password.tsx` | Set new password form |
| `src/components/auth/protected-route.tsx` | Route guard component |
| `src/components/auth/auth-layout.tsx` | Centered layout for auth pages |

#### Route Structure
```
Public Routes:
  /login           → LoginPage
  /register        → RegisterPage
  /forgot-password → ForgotPasswordPage
  /reset-password  → ResetPasswordPage

Protected Routes (require auth):
  /              → Dashboard
  /jobs          → Jobs
  /jobs/create   → Create Job
  /jobs/:id/edit → Edit Job
  /candidates    → Candidates
  /documents     → Documents
  /search        → Search/RAG
  /logs          → Logs
  /settings      → Settings
```

---

### Phase 2: Navigation Update

#### Sidebar Items
| Item | Icon | Route | Status |
|------|------|-------|--------|
| Dashboard | LayoutDashboardIcon | / | Keep |
| Jobs | BriefcaseIcon | /jobs | Keep |
| Candidates | UsersIcon | /candidates | Keep |
| Documents | FileTextIcon | /documents | **New** |
| Search | SearchIcon | /search | **Rename** |
| Logs | ClipboardListIcon | /logs | **New** |
| Settings | SettingsIcon | /settings | Keep |

---

### Phase 3: Documents Page

**Use Cases:** UC-03 (Search Documents), UC-04 (Filter Search)
**Requirements:** FR04, FR05, FR06

#### New Files
| File | Description |
|------|-------------|
| `src/pages/documents.tsx` | Main documents page |
| `src/components/documents/upload-dialog.tsx` | File upload modal |
| `src/components/documents/document-preview.tsx` | Document viewer |

#### Features
- File upload with drag-and-drop (PDF, DOCX, images)
- Document list/grid view with sorting
- Filter by type, date, processing status
- Document preview modal
- Delete document action
- Processing status indicator (OCR in progress)

---

### Phase 4: Search & RAG Page

**Use Cases:** UC-03 (Search), UC-05 (Export Excel)
**Requirements:** FR07, FR08, FR09, FR16

#### Changes
- Rename `analytics.tsx` → `search.tsx`

#### Features
- Natural language search input
- Semantic search results with relevance scores
- RAG chat interface for Q&A
- Source document citations
- Export results to Excel button

---

### Phase 5: Jobs Page Enhancement

**Use Cases:** UC-06 (Create Job), UC-07 (Edit/Delete Job)
**Requirements:** FR11, FR12

#### New Files
| File | Description |
|------|-------------|
| `src/pages/jobs/create.tsx` | Create job form |
| `src/pages/jobs/[id]/edit.tsx` | Edit job form |
| `src/components/jobs/job-form.tsx` | Reusable job form component |

#### Job Form Fields
- Title (required)
- Description (required, rich text)
- Required Skills (multi-select tags)
- Preferred Skills (optional)
- Education Level (select)
- Experience Range (min/max years)
- Location (text)
- Employment Type (Full-time, Part-time, Contract)
- Status (Draft, Active, Closed)

---

### Phase 6: Candidates Page Enhancement

**Use Cases:** UC-12 (Read Resumes)
**Requirements:** FR13, FR14, FR15, FR16

#### New Files
| File | Description |
|------|-------------|
| `src/components/candidates/resume-viewer.tsx` | Resume content modal |

#### Features
- Resume viewer modal (extracted content display)
- Shortlist button with confirmation
- Reject button with optional reason
- Export to Excel button
- Bulk actions (shortlist/reject multiple)
- Skills highlighting in resume view

---

### Phase 7: Email Integration

**Use Cases:** UC-08 (Receive Email), UC-09 (Sync Resumes)
**Requirements:** FR17, FR18

#### New Files
| File | Description |
|------|-------------|
| `src/components/settings/email-connection.tsx` | Email integration component |

#### Features
- Gmail OAuth connect button
- Connection status indicator (Connected/Not Connected)
- Sync now button
- Last sync timestamp
- Sync history list
- Disconnect option

---

### Phase 8: Logs Page

**Use Cases:** UC-10 (View Logs)
**Requirements:** FR19

#### New Files
| File | Description |
|------|-------------|
| `src/pages/logs.tsx` | Activity logs page |

#### Features
- Log entries table (timestamp, user, action, resource)
- Filter by date range
- Filter by action type
- Filter by user
- Search within logs
- Pagination

---

### Phase 9: Metadata Integration

**Use Cases:** UC-11 (View Metadata)
**Requirements:** FR20

#### Integration Points
- Document preview modal → Metadata panel
- Candidate view → Extracted skills, experience

#### Metadata Display
- Document type, upload date
- Extracted skills (tags)
- Experience summary
- Education details
- Contact information (for resumes)

---

## File Changes Summary

### New Files (16)

```
src/pages/auth/login.tsx
src/pages/auth/register.tsx
src/pages/auth/forgot-password.tsx
src/pages/auth/reset-password.tsx
src/pages/documents.tsx
src/pages/search.tsx
src/pages/logs.tsx
src/pages/jobs/create.tsx
src/pages/jobs/[id]/edit.tsx
src/components/auth/protected-route.tsx
src/components/auth/auth-layout.tsx
src/components/documents/upload-dialog.tsx
src/components/documents/document-preview.tsx
src/components/jobs/job-form.tsx
src/components/settings/email-connection.tsx
src/components/candidates/resume-viewer.tsx
```

### Modified Files (6)

```
src/router.tsx
src/main.tsx
src/providers/auth-provider.tsx
src/components/layout/app-sidebar.tsx
src/pages/candidates.tsx
src/pages/settings.tsx
```

### Deleted Files (1)

```
src/pages/analytics.tsx (replaced by search.tsx)
```

---

## Implementation Order

| Order | Phase | Description | Priority |
|-------|-------|-------------|----------|
| 1 | Phase 1 | Authentication (login, register, protected routes) | High |
| 2 | Phase 2 | Navigation update | High |
| 3 | Phase 3 | Documents page | High |
| 4 | Phase 4 | Search/RAG page | High |
| 5 | Phase 5 | Jobs enhancement | Medium |
| 6 | Phase 6 | Candidates enhancement | Medium |
| 7 | Phase 7 | Email integration | Medium |
| 8 | Phase 8 | Logs page | Low |
| 9 | Phase 9 | Metadata integration | Low |

---

## Technical Notes

- All pages will use mock data initially
- Form validation using browser validation + custom logic
- Consistent use of existing UI components
- Toast notifications for user feedback (Sonner)
- Mobile-responsive layouts throughout
- Dark mode support (already configured)

---

## SRS Requirements Coverage

| Requirement | Description | Phase |
|-------------|-------------|-------|
| FR01 | Login with email/password | Phase 1 |
| FR02 | Reset password | Phase 1 |
| FR03 | Restrict access unless authenticated | Phase 1 |
| FR04 | Upload resumes and documents | Phase 3 |
| FR05 | Extract text using OCR | Phase 3 |
| FR06 | Store documents for retrieval | Phase 3 |
| FR07 | Search using keywords/natural language | Phase 4 |
| FR08 | Search by skills, role, date | Phase 4 |
| FR09 | Display ranked search results | Phase 4 |
| FR10 | Filter documents by criteria | Phase 3 |
| FR11 | Create job descriptions | Phase 5 |
| FR12 | Edit job postings | Phase 5 |
| FR13 | View resume content | Phase 6 |
| FR14 | Shortlist candidates | Phase 6 |
| FR15 | Reject candidates | Phase 6 |
| FR16 | Export to Excel | Phase 4, 6 |
| FR17 | Connect email account | Phase 7 |
| FR18 | Sync resume attachments | Phase 7 |
| FR19 | View activity logs | Phase 8 |
| FR20 | View document metadata | Phase 9 |
