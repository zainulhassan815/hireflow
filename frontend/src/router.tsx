import { createBrowserRouter } from "react-router-dom";

import { AppLayout } from "@/components/layout/app-layout";
import { DashboardPage } from "@/pages/dashboard";
import { JobsPage } from "@/pages/jobs";
import { CandidatesPage } from "@/pages/candidates";
import { AnalyticsPage } from "@/pages/analytics";
import { SettingsPage } from "@/pages/settings";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <AppLayout />,
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
        path: "candidates",
        element: <CandidatesPage />,
      },
      {
        path: "analytics",
        element: <AnalyticsPage />,
      },
      {
        path: "settings",
        element: <SettingsPage />,
      },
    ],
  },
]);
