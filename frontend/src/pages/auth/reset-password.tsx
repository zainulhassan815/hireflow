import * as React from "react";
import { NavLink, useNavigate, useSearchParams } from "react-router-dom";
import {
  ArrowLeftIcon,
  CheckCircleIcon,
  EyeIcon,
  EyeOffIcon,
} from "lucide-react";

import { AuthLayout } from "@/components/auth/auth-layout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/providers/use-auth";
import { AuthError } from "@/providers/auth-errors";
import { toast } from "sonner";

export function ResetPasswordPage() {
  const [password, setPassword] = React.useState("");
  const [confirmPassword, setConfirmPassword] = React.useState("");
  const [showPassword, setShowPassword] = React.useState(false);
  const [isSubmitting, setIsSubmitting] = React.useState(false);
  const [isSuccess, setIsSuccess] = React.useState(false);

  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const token = searchParams.get("token");
  const { resetPassword } = useAuth();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!token) return;

    if (password !== confirmPassword) {
      toast.error("Passwords do not match");
      return;
    }

    if (password.length < 8) {
      toast.error("Password must be at least 8 characters");
      return;
    }

    setIsSubmitting(true);

    try {
      await resetPassword(token, password);
      setIsSuccess(true);
      toast.success("Password reset successfully");
    } catch (err) {
      const message =
        err instanceof AuthError ? err.message : "Failed to reset password";
      toast.error(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  if (!token) {
    return (
      <AuthLayout
        title="Invalid link"
        description="This password reset link is invalid or has expired"
      >
        <div className="space-y-4">
          <p className="text-muted-foreground text-center text-sm">
            Please request a new password reset link.
          </p>
          <Button
            className="w-full"
            onClick={() => navigate("/forgot-password")}
          >
            Request new link
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

  if (isSuccess) {
    return (
      <AuthLayout
        title="Password reset"
        description="Your password has been reset successfully"
      >
        <div className="space-y-6">
          <div className="bg-muted/50 flex flex-col items-center gap-4 rounded-lg p-6">
            <div className="flex size-12 items-center justify-center rounded-full bg-green-100 dark:bg-green-900/30">
              <CheckCircleIcon className="size-6 text-green-600 dark:text-green-400" />
            </div>
            <p className="text-muted-foreground text-center text-sm">
              You can now sign in with your new password.
            </p>
          </div>

          <Button className="w-full" onClick={() => navigate("/login")}>
            Sign in
          </Button>
        </div>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout
      title="Reset password"
      description="Enter your new password below"
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="password">New Password</Label>
          <div className="relative">
            <Input
              id="password"
              type={showPassword ? "text" : "password"}
              placeholder="Enter new password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="new-password"
              className="pr-10"
              autoFocus
            />
            <button
              type="button"
              onClick={() => setShowPassword(!showPassword)}
              className="text-muted-foreground hover:text-foreground absolute top-1/2 right-3 -translate-y-1/2"
            >
              {showPassword ? (
                <EyeOffIcon className="size-4" />
              ) : (
                <EyeIcon className="size-4" />
              )}
            </button>
          </div>
          <p className="text-muted-foreground text-xs">
            Must be at least 8 characters
          </p>
        </div>

        <div className="space-y-2">
          <Label htmlFor="confirmPassword">Confirm Password</Label>
          <Input
            id="confirmPassword"
            type={showPassword ? "text" : "password"}
            placeholder="Confirm new password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            required
            autoComplete="new-password"
          />
        </div>

        <Button type="submit" className="w-full" disabled={isSubmitting}>
          {isSubmitting ? "Resetting..." : "Reset password"}
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
