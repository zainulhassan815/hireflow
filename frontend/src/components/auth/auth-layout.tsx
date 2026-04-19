import { NavLink } from "react-router-dom";

interface AuthLayoutProps {
  children: React.ReactNode;
  title: string;
  description: string;
}

export function AuthLayout({ children, title, description }: AuthLayoutProps) {
  return (
    <div className="flex min-h-screen">
      {/* Left side - Branding */}
      <div className="bg-primary hidden w-1/2 flex-col justify-between p-12 lg:flex">
        <NavLink to="/" className="flex items-center gap-3">
          <div className="flex size-10 items-center justify-center bg-white">
            <span className="text-primary text-base font-bold">H</span>
          </div>
          <span className="text-lg font-semibold text-white">Hireflow</span>
        </NavLink>

        <div className="space-y-6">
          <h1 className="text-4xl leading-tight font-bold text-white">
            AI-Powered HR Screening
            <br />& Document Retrieval
          </h1>
          <p className="text-primary-foreground/80 max-w-md text-lg">
            Automate resume screening and enable intelligent document search
            using RAG technology. Reduce manual effort by up to 70%.
          </p>
        </div>

        <p className="text-primary-foreground/60 text-sm">
          Sharif College of Engineering & Technology
        </p>
      </div>

      {/* Right side - Form */}
      <div className="flex w-full items-center justify-center p-8 lg:w-1/2">
        <div className="w-full max-w-md space-y-8">
          {/* Mobile logo */}
          <div className="flex justify-center lg:hidden">
            <NavLink to="/" className="flex items-center gap-3">
              <div className="bg-primary flex size-10 items-center justify-center">
                <span className="text-base font-bold text-white">H</span>
              </div>
              <span className="text-lg font-semibold">Hireflow</span>
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
