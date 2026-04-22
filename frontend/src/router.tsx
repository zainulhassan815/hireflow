import { createBrowserRouter, Navigate } from "react-router-dom";

import { AppLayout } from "@/components/layout/app-layout";
import { ProtectedRoute } from "@/components/auth/protected-route";
import { PublicOnlyRoute } from "@/components/auth/public-only-route";
import { DashboardPage } from "@/pages/dashboard";
import { JobsPage } from "@/pages/jobs";
import { CreateJobPage } from "@/pages/jobs/create";
import { JobDetailPage } from "@/pages/jobs/detail";
import { EditJobPage } from "@/pages/jobs/edit";
import { CandidatesPage } from "@/pages/candidates";
import { DocumentsPage } from "@/pages/documents";
import { DocumentDetailPage } from "@/pages/documents/detail";
import { SearchPage } from "@/pages/search";
import { LogsPage } from "@/pages/logs";
import { SettingsPage } from "@/pages/settings";

// Auth pages
import { LoginPage } from "@/pages/auth/login";
import { RegisterPage } from "@/pages/auth/register";
import { ForgotPasswordPage } from "@/pages/auth/forgot-password";
import { ResetPasswordPage } from "@/pages/auth/reset-password";

export const router = createBrowserRouter([
  // Public auth routes (redirect to app if already signed in)
  {
    path: "/login",
    element: (
      <PublicOnlyRoute>
        <LoginPage />
      </PublicOnlyRoute>
    ),
  },
  {
    path: "/register",
    element: (
      <PublicOnlyRoute>
        <RegisterPage />
      </PublicOnlyRoute>
    ),
  },
  {
    path: "/forgot-password",
    element: (
      <PublicOnlyRoute>
        <ForgotPasswordPage />
      </PublicOnlyRoute>
    ),
  },
  {
    path: "/reset-password",
    element: <ResetPasswordPage />,
  },

  // Protected routes
  {
    path: "/",
    element: (
      <ProtectedRoute>
        <AppLayout />
      </ProtectedRoute>
    ),
    children: [
      {
        index: true,
        element: <DashboardPage />,
        handle: { title: "Dashboard" },
      },
      {
        path: "jobs",
        element: <JobsPage />,
        handle: { title: "Jobs" },
      },
      {
        path: "jobs/create",
        element: <CreateJobPage />,
        handle: { title: "New job" },
      },
      {
        path: "jobs/:id",
        element: <JobDetailPage />,
        handle: { title: "Job" },
      },
      {
        path: "jobs/:id/edit",
        element: <EditJobPage />,
        handle: { title: "Edit job" },
      },
      {
        path: "candidates",
        element: <CandidatesPage />,
        handle: { title: "Candidates" },
      },
      {
        path: "documents",
        element: <DocumentsPage />,
        handle: { title: "Documents" },
      },
      {
        path: "documents/:id",
        element: <DocumentDetailPage />,
        handle: { title: "Document" },
      },
      {
        path: "search",
        element: <SearchPage />,
        handle: { title: "Search" },
      },
      {
        path: "logs",
        element: <LogsPage />,
        handle: { title: "Logs" },
      },
      {
        path: "settings",
        element: <SettingsPage />,
        handle: { title: "Settings" },
      },
    ],
  },

  // Catch-all redirect
  {
    path: "*",
    element: <Navigate to="/" replace />,
  },
]);
