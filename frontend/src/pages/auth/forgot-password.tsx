import * as React from "react";
import { NavLink } from "react-router-dom";
import { ArrowLeftIcon, MailIcon } from "lucide-react";

import { AuthLayout } from "@/components/auth/auth-layout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";

export function ForgotPasswordPage() {
  const [email, setEmail] = React.useState("");
  const [isSubmitting, setIsSubmitting] = React.useState(false);
  const [isEmailSent, setIsEmailSent] = React.useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);

    try {
      // TODO: Implement actual password reset request
      await new Promise((resolve) => setTimeout(resolve, 1000));
      setIsEmailSent(true);
      toast.success("Reset link sent to your email");
    } catch {
      toast.error("Failed to send reset link");
    } finally {
      setIsSubmitting(false);
    }
  };

  if (isEmailSent) {
    return (
      <AuthLayout
        title="Check your email"
        description="We've sent a password reset link to your email"
      >
        <div className="space-y-6">
          <div className="bg-muted/50 flex flex-col items-center gap-4 rounded-lg p-6">
            <div className="bg-primary/10 flex size-12 items-center justify-center rounded-full">
              <MailIcon className="text-primary size-6" />
            </div>
            <div className="text-center">
              <p className="font-medium">{email}</p>
              <p className="text-muted-foreground mt-1 text-sm">
                Click the link in the email to reset your password. If you don't
                see it, check your spam folder.
              </p>
            </div>
          </div>

          <Button
            variant="outline"
            className="w-full"
            onClick={() => setIsEmailSent(false)}
          >
            Try a different email
          </Button>

          <p className="text-muted-foreground text-center text-sm">
            <NavLink
              to="/login"
              className="text-primary inline-flex items-center gap-1 hover:underline"
            >
              <ArrowLeftIcon className="size-3" />
              Back to login
            </NavLink>
          </p>
        </div>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout
      title="Forgot password?"
      description="Enter your email and we'll send you a reset link"
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="email">Email</Label>
          <Input
            id="email"
            type="email"
            placeholder="name@company.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoComplete="email"
            autoFocus
          />
        </div>

        <Button type="submit" className="w-full" disabled={isSubmitting}>
          {isSubmitting ? "Sending..." : "Send reset link"}
        </Button>
      </form>

      <p className="text-muted-foreground text-center text-sm">
        <NavLink
          to="/login"
          className="text-primary inline-flex items-center gap-1 hover:underline"
        >
          <ArrowLeftIcon className="size-3" />
          Back to login
        </NavLink>
      </p>
    </AuthLayout>
  );
}
