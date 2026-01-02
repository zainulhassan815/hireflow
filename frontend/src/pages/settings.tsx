import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
import { Typography } from "@/components/ui/typography";
import { EmailConnection } from "@/components/settings/email-connection";

export function SettingsPage() {
  return (
    <div className="flex flex-col gap-6">
      <div>
        <Typography variant="h3">Settings</Typography>
        <Typography variant="muted">
          Manage your account and preferences
        </Typography>
      </div>

      <div className="grid gap-6">
        {/* Profile */}
        <Card>
          <CardHeader>
            <Typography variant="h5">Profile</Typography>
            <Typography variant="muted">
              Your personal information and account details
            </Typography>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="name">Name</Label>
                <Input id="name" defaultValue="HR Manager" />
              </div>
              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <Input id="email" type="email" defaultValue="hr@company.com" />
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="company">Company</Label>
              <Input id="company" defaultValue="Acme Corporation" />
            </div>
            <Button>Save Changes</Button>
          </CardContent>
        </Card>

        {/* Email Integration */}
        <EmailConnection />

        {/* Notifications */}
        <Card>
          <CardHeader>
            <Typography variant="h5">Notifications</Typography>
            <Typography variant="muted">
              Configure how you receive notifications
            </Typography>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Typography variant="label">New Applications</Typography>
                <Typography variant="muted">
                  Get notified when a new candidate applies
                </Typography>
              </div>
              <Switch defaultChecked />
            </div>
            <Separator />
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Typography variant="label">Daily Digest</Typography>
                <Typography variant="muted">
                  Receive a daily summary of applications
                </Typography>
              </div>
              <Switch defaultChecked />
            </div>
            <Separator />
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Typography variant="label">AI Recommendations</Typography>
                <Typography variant="muted">
                  Get notified about high-match candidates
                </Typography>
              </div>
              <Switch defaultChecked />
            </div>
          </CardContent>
        </Card>

        {/* API Configuration */}
        <Card>
          <CardHeader>
            <Typography variant="h5">API Configuration</Typography>
            <Typography variant="muted">
              Configure API keys for AI services
            </Typography>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="openai-key">OpenAI API Key</Label>
              <Input
                id="openai-key"
                type="password"
                placeholder="sk-..."
                defaultValue="sk-••••••••••••••••••••"
              />
              <Typography variant="muted" className="text-xs">
                Used for embeddings and AI-powered search
              </Typography>
            </div>
            <Button>Update API Key</Button>
          </CardContent>
        </Card>

        {/* Danger Zone */}
        <Card className="border-destructive/50">
          <CardHeader>
            <Typography variant="h5" className="text-destructive">
              Danger Zone
            </Typography>
            <Typography variant="muted">
              Irreversible actions for your account
            </Typography>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Typography variant="small" className="font-medium">
                  Delete All Data
                </Typography>
                <Typography variant="muted">
                  Permanently delete all jobs, candidates, and applications
                </Typography>
              </div>
              <Button variant="destructive" size="sm">
                Delete All
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
