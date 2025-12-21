# Component Patterns Guide

Based on composition principles from modern React development. The goal: build components that scale without becoming unmaintainable messes of boolean props and conditions.

## The Problem

```tsx
// ❌ This is what happens over time
<CandidateForm
  isEditing={true}
  isQuickEdit={false}
  showTerms={false}
  showWelcome={false}
  hideEducation={true}
  hideExperience={false}
  onlyShowName={false}
  isSlugRequired={false}
  redirectOnSuccess={false}
  showCancelButton={true}
  submitLabel="Save"
  // ... 20 more props
/>
```

**If you have a boolean prop that determines which component tree gets rendered from the parent, there's a better way.**

---

## Core Principle: Composition Over Configuration

Instead of one monolith with 30 props, create composable pieces:

```tsx
// ✅ Composition approach
<CandidateFormProvider candidate={existingCandidate} onSubmit={handleUpdate}>
  <CandidateFormFrame>
    <CandidateFormHeader title="Edit Candidate" />
    <CandidateNameField />
    <CandidateEmailField />
    <CandidateSkillsField />
    {/* No education field - we just don't render it */}
    <CandidateFormFooter>
      <CancelButton />
      <SubmitButton>Save Changes</SubmitButton>
    </CandidateFormFooter>
  </CandidateFormFrame>
</CandidateFormProvider>
```

---

## Pattern 1: Compound Components

Build components like Radix UI - a Provider with composable children.

### Example: Job Application Card

```tsx
// ❌ Monolith approach
<ApplicationCard
  application={app}
  showMatchScore={true}
  showSkillBreakdown={true}
  showActions={true}
  isCompact={false}
  onShortlist={handleShortlist}
  onReject={handleReject}
  onView={handleView}
  showQuickActions={true}
  hideEmail={false}
/>

// ✅ Compound component approach
<ApplicationCard.Root application={app}>
  <ApplicationCard.Header>
    <ApplicationCard.CandidateName />
    <ApplicationCard.MatchScore />
  </ApplicationCard.Header>
  <ApplicationCard.Content>
    <ApplicationCard.SkillMatch />
    <ApplicationCard.ExperienceSummary />
  </ApplicationCard.Content>
  <ApplicationCard.Actions>
    <ApplicationCard.ViewButton />
    <ApplicationCard.ShortlistButton />
    <ApplicationCard.RejectButton />
  </ApplicationCard.Actions>
</ApplicationCard.Root>
```

### Implementation

```tsx
// src/components/features/applications/application-card.tsx
import * as React from "react";
import { createContext, useContext } from "react";
import { cn } from "@/lib/utils";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { MatchScoreBadge } from "@/components/custom/match-score-badge";
import type { ApplicationResponse } from "@/api/generated";

// Context
interface ApplicationCardContext {
  application: ApplicationResponse;
  onShortlist?: () => void;
  onReject?: () => void;
  onView?: () => void;
}

const ApplicationCardContext = createContext<ApplicationCardContext | null>(
  null
);

function useApplicationCard() {
  const context = useContext(ApplicationCardContext);
  if (!context) {
    throw new Error(
      "ApplicationCard components must be used within ApplicationCard.Root"
    );
  }
  return context;
}

// Root Provider
interface RootProps {
  application: ApplicationResponse;
  onShortlist?: () => void;
  onReject?: () => void;
  onView?: () => void;
  children: React.ReactNode;
  className?: string;
}

function Root({
  application,
  onShortlist,
  onReject,
  onView,
  children,
  className,
}: RootProps) {
  return (
    <ApplicationCardContext.Provider
      value={{ application, onShortlist, onReject, onView }}
    >
      <Card className={cn("transition-shadow hover:shadow-md", className)}>
        {children}
      </Card>
    </ApplicationCardContext.Provider>
  );
}

// Composable pieces
function Header({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <CardHeader
      className={cn(
        "flex flex-row items-start justify-between gap-4",
        className
      )}
    >
      {children}
    </CardHeader>
  );
}

function CandidateName({ className }: { className?: string }) {
  const { application } = useApplicationCard();
  return (
    <div className={className}>
      <h3 className="font-semibold leading-none">
        {application.candidate_name}
      </h3>
      {application.email && (
        <p className="mt-1 text-sm text-muted-foreground">
          {application.email}
        </p>
      )}
    </div>
  );
}

function MatchScore({ showBreakdown = false }: { showBreakdown?: boolean }) {
  const { application } = useApplicationCard();
  if (!application.match_score) return null;

  return (
    <div className="text-right">
      <MatchScoreBadge score={application.match_score} />
      {showBreakdown && application.breakdown && (
        <div className="mt-2 space-y-1 text-xs text-muted-foreground">
          <div>
            Skills: {Math.round(application.breakdown.skill_match * 100)}%
          </div>
          <div>
            Experience:{" "}
            {Math.round(application.breakdown.experience_match * 100)}%
          </div>
        </div>
      )}
    </div>
  );
}

function Content({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <CardContent className={className}>{children}</CardContent>;
}

function SkillMatch() {
  const { application } = useApplicationCard();
  // Render skill match visualization
  return null; // Implementation
}

function ExperienceSummary() {
  const { application } = useApplicationCard();
  // Render experience summary
  return null; // Implementation
}

function Actions({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex items-center gap-2 border-t p-4", className)}>
      {children}
    </div>
  );
}

function ViewButton() {
  const { onView } = useApplicationCard();
  if (!onView) return null;
  return (
    <Button variant="outline" size="sm" onClick={onView}>
      View Details
    </Button>
  );
}

function ShortlistButton() {
  const { onShortlist, application } = useApplicationCard();
  if (!onShortlist || application.status === "shortlisted") return null;
  return (
    <Button variant="default" size="sm" onClick={onShortlist}>
      Shortlist
    </Button>
  );
}

function RejectButton() {
  const { onReject, application } = useApplicationCard();
  if (!onReject || application.status === "rejected") return null;
  return (
    <Button variant="ghost" size="sm" onClick={onReject}>
      Reject
    </Button>
  );
}

// Export as namespace
export const ApplicationCard = {
  Root,
  Header,
  CandidateName,
  MatchScore,
  Content,
  SkillMatch,
  ExperienceSummary,
  Actions,
  ViewButton,
  ShortlistButton,
  RejectButton,
};
```

### Usage in Different Contexts

```tsx
// Full card in candidate list
<ApplicationCard.Root application={app} onShortlist={...} onReject={...} onView={...}>
  <ApplicationCard.Header>
    <ApplicationCard.CandidateName />
    <ApplicationCard.MatchScore showBreakdown />
  </ApplicationCard.Header>
  <ApplicationCard.Content>
    <ApplicationCard.SkillMatch />
  </ApplicationCard.Content>
  <ApplicationCard.Actions>
    <ApplicationCard.ViewButton />
    <ApplicationCard.ShortlistButton />
    <ApplicationCard.RejectButton />
  </ApplicationCard.Actions>
</ApplicationCard.Root>

// Compact card in sidebar
<ApplicationCard.Root application={app} onView={handleView}>
  <ApplicationCard.Header>
    <ApplicationCard.CandidateName />
    <ApplicationCard.MatchScore />
  </ApplicationCard.Header>
  {/* No content, no actions - just don't render them */}
</ApplicationCard.Root>

// Card with custom actions
<ApplicationCard.Root application={app}>
  <ApplicationCard.Header>
    <ApplicationCard.CandidateName />
  </ApplicationCard.Header>
  <ApplicationCard.Actions>
    {/* Custom action - not part of the compound component */}
    <Button onClick={handleScheduleInterview}>Schedule Interview</Button>
  </ApplicationCard.Actions>
</ApplicationCard.Root>
```

---

## Pattern 2: Lifting State for Sibling Access

When components outside your main UI need access to state/actions, lift the Provider up.

### Example: Document Search with External Actions

```tsx
// ❌ Problem: Search button is outside the search form
// How do you access the search state?

function SearchPage() {
  return (
    <div>
      <header>
        <h1>Search</h1>
        <Button>Export Results</Button> {/* Needs access to results! */}
      </header>
      <SearchForm /> {/* Has the state */}
      <SearchResults /> {/* Needs the state */}
    </div>
  );
}

// ✅ Solution: Lift the provider
function SearchPage() {
  return (
    <SearchProvider>
      <header>
        <h1>Search</h1>
        <ExportResultsButton /> {/* Can now access context */}
      </header>
      <SearchForm />
      <SearchResults />
    </SearchProvider>
  );
}
```

### Implementation

```tsx
// src/components/features/search/search-provider.tsx
import * as React from "react";
import { createContext, useContext, useState, useCallback } from "react";
import { useMutation } from "@tanstack/react-query";
import { searchSearchDocuments } from "@/api/generated";
import type {
  SearchRequest,
  SearchResponse,
  SearchResultItem,
} from "@/api/generated";

interface SearchState {
  query: string;
  filters: SearchRequest["filters"];
  results: SearchResultItem[];
  total: number;
  isSearching: boolean;
}

interface SearchActions {
  setQuery: (query: string) => void;
  setFilters: (filters: SearchRequest["filters"]) => void;
  search: () => void;
  clear: () => void;
}

interface SearchContextValue {
  state: SearchState;
  actions: SearchActions;
}

const SearchContext = createContext<SearchContextValue | null>(null);

export function useSearch() {
  const context = useContext(SearchContext);
  if (!context) {
    throw new Error("useSearch must be used within SearchProvider");
  }
  return context;
}

// Convenience hooks
export function useSearchState() {
  return useSearch().state;
}

export function useSearchActions() {
  return useSearch().actions;
}

interface SearchProviderProps {
  children: React.ReactNode;
  initialQuery?: string;
}

export function SearchProvider({
  children,
  initialQuery = "",
}: SearchProviderProps) {
  const [query, setQuery] = useState(initialQuery);
  const [filters, setFilters] = useState<SearchRequest["filters"]>({});
  const [results, setResults] = useState<SearchResultItem[]>([]);
  const [total, setTotal] = useState(0);

  const searchMutation = useMutation({
    mutationFn: searchSearchDocuments,
    onSuccess: (response) => {
      if (response.data) {
        setResults(response.data.results);
        setTotal(response.data.total);
      }
    },
  });

  const search = useCallback(() => {
    if (!query.trim()) return;
    searchMutation.mutate({ body: { query, filters, limit: 20, offset: 0 } });
  }, [query, filters, searchMutation]);

  const clear = useCallback(() => {
    setQuery("");
    setFilters({});
    setResults([]);
    setTotal(0);
  }, []);

  const value: SearchContextValue = {
    state: {
      query,
      filters,
      results,
      total,
      isSearching: searchMutation.isPending,
    },
    actions: {
      setQuery,
      setFilters,
      search,
      clear,
    },
  };

  return (
    <SearchContext.Provider value={value}>{children}</SearchContext.Provider>
  );
}
```

### Components Using the Provider

```tsx
// src/components/features/search/search-input.tsx
import { useSearchState, useSearchActions } from "./search-provider";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Search, X } from "lucide-react";

export function SearchInput() {
  const { query, isSearching } = useSearchState();
  const { setQuery, search, clear } = useSearchActions();

  return (
    <div className="flex gap-2">
      <div className="relative flex-1">
        <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && search()}
          placeholder="Search documents..."
          className="pl-10"
        />
        {query && (
          <button
            onClick={clear}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
          >
            <X className="size-4" />
          </button>
        )}
      </div>
      <Button onClick={search} disabled={isSearching}>
        {isSearching ? "Searching..." : "Search"}
      </Button>
    </div>
  );
}

// src/components/features/search/search-results.tsx
import { useSearchState } from "./search-provider";
import { DocumentCard } from "@/components/custom/document-card";

export function SearchResults() {
  const { results, total, isSearching } = useSearchState();

  if (isSearching) return <SearchResultsSkeleton />;
  if (results.length === 0) return <EmptySearchResults />;

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">{total} results found</p>
      {results.map((result) => (
        <SearchResultCard key={result.document_id} result={result} />
      ))}
    </div>
  );
}

// src/components/features/search/export-results-button.tsx
// This component is OUTSIDE the search form but can still access results!
import { useSearchState } from "./search-provider";
import { Button } from "@/components/ui/button";
import { Download } from "lucide-react";

export function ExportResultsButton() {
  const { results } = useSearchState();

  if (results.length === 0) return null;

  const handleExport = () => {
    // Export logic
  };

  return (
    <Button variant="outline" onClick={handleExport}>
      <Download className="mr-2 size-4" />
      Export {results.length} Results
    </Button>
  );
}
```

### Page Composition

```tsx
// src/pages/search.tsx
import { SearchProvider } from "@/components/features/search/search-provider";
import { SearchInput } from "@/components/features/search/search-input";
import { SearchFilters } from "@/components/features/search/search-filters";
import { SearchResults } from "@/components/features/search/search-results";
import { ExportResultsButton } from "@/components/features/search/export-results-button";

export function SearchPage() {
  return (
    <SearchProvider>
      <div className="container py-6">
        <header className="mb-6 flex items-center justify-between">
          <h1 className="text-2xl font-bold">Search Documents</h1>
          <ExportResultsButton /> {/* Works because it's inside SearchProvider */}
        </header>

        <div className="mb-6 space-y-4">
          <SearchInput />
          <SearchFilters />
        </div>

        <SearchResults />
      </div>
    </SearchProvider>
  );
}
```

---

## Pattern 3: Swappable State Implementations

The provider defines the interface, but the implementation can vary.

### Example: Job Form with Different State Sources

```tsx
// Create job - uses local state
<JobFormProvider
  initialState={{ title: "", description: "", required_skills: [] }}
  onSubmit={handleCreate}
>
  <JobForm />
</JobFormProvider>

// Edit job - uses server state
<JobFormProvider
  initialState={existingJob}
  onSubmit={handleUpdate}
>
  <JobForm />
</JobFormProvider>

// The JobForm component is identical in both cases!
// It just reads from context - doesn't care where state comes from.
```

### Implementation with Flexible State

```tsx
// src/components/features/jobs/job-form-provider.tsx
import * as React from "react";
import { createContext, useContext, useState, useCallback } from "react";
import type { CreateJobRequest, JobResponse } from "@/api/generated";

type JobFormData = CreateJobRequest;

interface JobFormState {
  data: JobFormData;
  isDirty: boolean;
  errors: Record<string, string>;
}

interface JobFormActions {
  updateField: <K extends keyof JobFormData>(
    field: K,
    value: JobFormData[K]
  ) => void;
  setErrors: (errors: Record<string, string>) => void;
  reset: () => void;
  submit: () => Promise<void>;
}

interface JobFormMeta {
  isSubmitting: boolean;
  isEdit: boolean;
}

interface JobFormContextValue {
  state: JobFormState;
  actions: JobFormActions;
  meta: JobFormMeta;
}

const JobFormContext = createContext<JobFormContextValue | null>(null);

export function useJobForm() {
  const context = useContext(JobFormContext);
  if (!context) {
    throw new Error("useJobForm must be used within JobFormProvider");
  }
  return context;
}

interface JobFormProviderProps {
  children: React.ReactNode;
  initialState?: Partial<JobFormData>;
  existingJob?: JobResponse; // For edit mode
  onSubmit: (data: JobFormData) => Promise<void>;
}

const defaultState: JobFormData = {
  title: "",
  description: "",
  required_skills: [],
  preferred_skills: [],
  education_level: undefined,
  experience_min: 0,
  experience_max: undefined,
  location: undefined,
};

export function JobFormProvider({
  children,
  initialState,
  existingJob,
  onSubmit,
}: JobFormProviderProps) {
  const isEdit = !!existingJob;

  // Merge initial state
  const mergedInitial: JobFormData = {
    ...defaultState,
    ...initialState,
    ...(existingJob && {
      title: existingJob.title,
      description: existingJob.description,
      required_skills: existingJob.required_skills,
      preferred_skills: existingJob.preferred_skills,
      education_level: existingJob.education_level ?? undefined,
      experience_min: existingJob.experience_min,
      experience_max: existingJob.experience_max ?? undefined,
      location: existingJob.location ?? undefined,
    }),
  };

  const [data, setData] = useState<JobFormData>(mergedInitial);
  const [isDirty, setIsDirty] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);

  const updateField = useCallback(
    <K extends keyof JobFormData>(field: K, value: JobFormData[K]) => {
      setData((prev) => ({ ...prev, [field]: value }));
      setIsDirty(true);
      // Clear field error on change
      setErrors((prev) => {
        const next = { ...prev };
        delete next[field];
        return next;
      });
    },
    []
  );

  const reset = useCallback(() => {
    setData(mergedInitial);
    setIsDirty(false);
    setErrors({});
  }, [mergedInitial]);

  const submit = useCallback(async () => {
    setIsSubmitting(true);
    try {
      await onSubmit(data);
      setIsDirty(false);
    } finally {
      setIsSubmitting(false);
    }
  }, [data, onSubmit]);

  const value: JobFormContextValue = {
    state: { data, isDirty, errors },
    actions: { updateField, setErrors, reset, submit },
    meta: { isSubmitting, isEdit },
  };

  return (
    <JobFormContext.Provider value={value}>{children}</JobFormContext.Provider>
  );
}
```

### Form Components (Agnostic to State Source)

```tsx
// src/components/features/jobs/job-form.tsx
import { useJobForm } from "./job-form-provider";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { SkillsInput } from "@/components/custom/skills-input";

export function JobTitleField() {
  const { state, actions } = useJobForm();

  return (
    <div className="space-y-2">
      <Label htmlFor="title">Job Title</Label>
      <Input
        id="title"
        value={state.data.title}
        onChange={(e) => actions.updateField("title", e.target.value)}
        placeholder="e.g., Senior Python Developer"
      />
      {state.errors.title && (
        <p className="text-sm text-destructive">{state.errors.title}</p>
      )}
    </div>
  );
}

export function JobDescriptionField() {
  const { state, actions } = useJobForm();

  return (
    <div className="space-y-2">
      <Label htmlFor="description">Description</Label>
      <Textarea
        id="description"
        value={state.data.description}
        onChange={(e) => actions.updateField("description", e.target.value)}
        placeholder="Describe the role and responsibilities..."
        rows={6}
      />
      {state.errors.description && (
        <p className="text-sm text-destructive">{state.errors.description}</p>
      )}
    </div>
  );
}

export function JobSkillsField() {
  const { state, actions } = useJobForm();

  return (
    <div className="space-y-2">
      <Label>Required Skills</Label>
      <SkillsInput
        value={state.data.required_skills}
        onChange={(skills) => actions.updateField("required_skills", skills)}
        placeholder="Add required skills..."
      />
    </div>
  );
}

export function JobFormActions() {
  const { state, actions, meta } = useJobForm();

  return (
    <div className="flex items-center justify-end gap-3">
      {state.isDirty && (
        <Button variant="ghost" onClick={actions.reset}>
          Reset
        </Button>
      )}
      <Button onClick={actions.submit} disabled={meta.isSubmitting}>
        {meta.isSubmitting
          ? "Saving..."
          : meta.isEdit
          ? "Update Job"
          : "Create Job"}
      </Button>
    </div>
  );
}
```

### Usage: Create vs Edit

```tsx
// Create Job Page
function CreateJobPage() {
  const navigate = useNavigate();
  const createJob = useCreateJob();

  const handleSubmit = async (data: CreateJobRequest) => {
    await createJob.mutateAsync(data);
    navigate("/jobs");
  };

  return (
    <JobFormProvider onSubmit={handleSubmit}>
      <Card>
        <CardHeader>
          <CardTitle>Create New Job</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          <JobTitleField />
          <JobDescriptionField />
          <JobSkillsField />
          <JobExperienceField />
          <JobLocationField />
        </CardContent>
        <CardFooter>
          <JobFormActions />
        </CardFooter>
      </Card>
    </JobFormProvider>
  );
}

// Edit Job Page
function EditJobPage() {
  const { jobId } = useParams();
  const { data: job } = useJob(jobId);
  const updateJob = useUpdateJob();
  const navigate = useNavigate();

  if (!job) return <LoadingSkeleton />;

  const handleSubmit = async (data: CreateJobRequest) => {
    await updateJob.mutateAsync({ jobId, data });
    navigate("/jobs");
  };

  return (
    <JobFormProvider existingJob={job} onSubmit={handleSubmit}>
      <Card>
        <CardHeader>
          <CardTitle>Edit Job</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Exact same components! */}
          <JobTitleField />
          <JobDescriptionField />
          <JobSkillsField />
          <JobExperienceField />
          <JobLocationField />
        </CardContent>
        <CardFooter>
          <JobFormActions /> {/* Automatically shows "Update Job" */}
        </CardFooter>
      </Card>
    </JobFormProvider>
  );
}
```

---

## Pattern 4: JSX Over Configuration Arrays

Don't use arrays with conditions. Use JSX.

```tsx
// ❌ Array-based actions (nightmare to maintain)
const actions = [
  { id: "view", label: "View", icon: Eye, show: true },
  { id: "edit", label: "Edit", icon: Pencil, show: canEdit },
  {
    id: "delete",
    label: "Delete",
    icon: Trash,
    show: canDelete,
    variant: "destructive",
  },
  { id: "divider", type: "divider", show: canEdit || canDelete },
  { id: "export", label: "Export", icon: Download, show: hasResults },
];

// Then somewhere else, a messy loop:
{
  actions
    .filter((a) => a.show)
    .map((action) =>
      action.type === "divider" ? (
        <Divider key={action.id} />
      ) : (
        <ActionButton key={action.id} {...action} />
      )
    );
}

// ✅ JSX is the best abstraction for UI
<DropdownMenu>
  <DropdownMenuContent>
    <DropdownMenuItem onClick={handleView}>
      <Eye className="mr-2 size-4" />
      View
    </DropdownMenuItem>

    {canEdit && (
      <DropdownMenuItem onClick={handleEdit}>
        <Pencil className="mr-2 size-4" />
        Edit
      </DropdownMenuItem>
    )}

    {canDelete && (
      <>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={handleDelete} className="text-destructive">
          <Trash className="mr-2 size-4" />
          Delete
        </DropdownMenuItem>
      </>
    )}
  </DropdownMenuContent>
</DropdownMenu>;
```

---

## Anti-Patterns to Avoid

### 1. Boolean Props for Rendering

```tsx
// ❌ Bad
<UserForm isEditing={true} hideTerms={true} hideWelcome={true} />

// ✅ Good - Create distinct components
<EditUserForm />  // Different component, different tree
```

### 2. Prop Drilling Through Many Levels

```tsx
// ❌ Bad
<Page onSubmit={handleSubmit}>
  <Section onSubmit={handleSubmit}>
    <Form onSubmit={handleSubmit}>
      <Footer onSubmit={handleSubmit}>
        <SubmitButton onSubmit={handleSubmit} />

// ✅ Good - Use context
<FormProvider onSubmit={handleSubmit}>
  <Page>
    <Section>
      <Form>
        <Footer>
          <SubmitButton /> {/* Gets onSubmit from context */}
```

### 3. Render Props for Static Differences

```tsx
// ❌ Bad - Using render props for what should be composition
<Card
  renderHeader={() => <CustomHeader />}
  renderFooter={() => <CustomFooter />}
  renderActions={() => <CustomActions />}
/>

// ✅ Good - Just use children
<Card>
  <Card.Header>
    <CustomHeader />
  </Card.Header>
  <Card.Footer>
    <CustomFooter />
    <CustomActions />
  </Card.Footer>
</Card>
```

### 4. God Components

```tsx
// ❌ Bad - One component handling everything
function CandidateManager({ mode, view, filters, sorting, pagination, selection, ... }) {
  // 500 lines of conditions
}

// ✅ Good - Compose smaller pieces
<CandidateProvider filters={filters}>
  <CandidateToolbar>
    <CandidateSearch />
    <CandidateFilters />
    <CandidateSorting />
  </CandidateToolbar>
  <CandidateList view={view} />
  <CandidatePagination />
</CandidateProvider>
```

---

## Summary

1. **Composition over configuration** - Build compound components with Provider + composable pieces
2. **Lift state up** - Move Provider higher so siblings can access state/actions
3. **Interface vs implementation** - Provider defines the contract, implementation can vary
4. **JSX is the abstraction** - Don't use config arrays, just render JSX
5. **Avoid boolean props** - If a prop determines the entire tree, make separate components

> "The next time you're 15 booleans deep into your component props, just remember: composition is all you need."
