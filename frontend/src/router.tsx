import { createBrowserRouter, Navigate } from "react-router-dom";

import { AppLayout } from "@/components/layout/app-layout";
import { ProtectedRoute } from "@/components/auth/protected-route";
import { DashboardPage } from "@/pages/dashboard";
import { JobsPage } from "@/pages/jobs";
import { CreateJobPage } from "@/pages/jobs/create";
import { EditJobPage } from "@/pages/jobs/edit";
import { CandidatesPage } from "@/pages/candidates";
import { DocumentsPage } from "@/pages/documents";
import { SearchPage } from "@/pages/search";
import { LogsPage } from "@/pages/logs";
import { SettingsPage } from "@/pages/settings";

// Auth pages
import { LoginPage } from "@/pages/auth/login";
import { RegisterPage } from "@/pages/auth/register";
import { ForgotPasswordPage } from "@/pages/auth/forgot-password";
import { ResetPasswordPage } from "@/pages/auth/reset-password";

export const router = createBrowserRouter([
  // Public auth routes
  {
    path: "/login",
    element: <LoginPage />,
  },
  {
    path: "/register",
    element: <RegisterPage />,
  },
  {
    path: "/forgot-password",
    element: <ForgotPasswordPage />,
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
      },
      {
        path: "jobs",
        element: <JobsPage />,
      },
      {
        path: "jobs/create",
        element: <CreateJobPage />,
      },
      {
        path: "jobs/:id/edit",
        element: <EditJobPage />,
      },
      {
        path: "candidates",
        element: <CandidatesPage />,
      },
      {
        path: "documents",
        element: <DocumentsPage />,
      },
      {
        path: "search",
        element: <SearchPage />,
      },
      {
        path: "logs",
        element: <LogsPage />,
      },
      {
        path: "settings",
        element: <SettingsPage />,
      },
    ],
  },

  // Catch-all redirect
  {
    path: "*",
    element: <Navigate to="/" replace />,
  },
]);
