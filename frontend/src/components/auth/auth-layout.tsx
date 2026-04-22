import { NavLink } from "react-router-dom";

import { Logo } from "@/components/ui/logo";
import { useDocumentTitle } from "@/hooks/use-document-title";

interface AuthLayoutProps {
  children: React.ReactNode;
  title: string;
  description: string;
}

export function AuthLayout({ children, title, description }: AuthLayoutProps) {
  useDocumentTitle(title);
  return (
    <div className="flex min-h-screen">
      {/* Left side - Branding */}
      <div className="bg-primary hidden w-1/2 flex-col justify-between p-12 lg:flex">
        <NavLink to="/" className="flex items-center gap-3">
          <div className="flex size-10 items-center justify-center rounded-md bg-white p-1.5">
            <Logo className="size-full" />
          </div>
          <span className="font-display text-lg font-semibold tracking-[-0.01em] text-white">
            Hireflow
          </span>
        </NavLink>

        <div className="space-y-6">
          <h1 className="font-display text-5xl leading-[1.05] font-semibold tracking-[-0.02em] text-white">
            Hiring,
            <br />
            without the paperwork.
          </h1>
          <p className="text-primary-foreground/80 max-w-[50ch] text-lg leading-[1.6]">
            Upload the stack. Search the way a person reads. Keep the shortlist
            you can defend.
          </p>
        </div>

        <div aria-hidden />
      </div>

      {/* Right side - Form */}
      <div className="flex w-full items-center justify-center p-8 lg:w-1/2">
        <div className="w-full max-w-md space-y-8">
          {/* Mobile logo */}
          <div className="flex justify-center lg:hidden">
            <NavLink to="/" className="flex items-center gap-3">
              <Logo className="size-10 shrink-0" />
              <span className="font-display text-lg font-semibold tracking-[-0.01em]">
                Hireflow
              </span>
            </NavLink>
          </div>

          <div className="space-y-2 text-center">
            <h2 className="text-2xl font-semibold tracking-tight">{title}</h2>
            <p className="text-muted-foreground text-sm">{description}</p>
          </div>

          {children}
        </div>
      </div>
    </div>
  );
}
