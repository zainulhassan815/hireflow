import * as React from "react";
import { XIcon } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Typography } from "@/components/ui/typography";

// Mirrors the backend job contract (CreateJobRequest / UpdateJobRequest).
// Status is deliberately absent — it's a validated lifecycle action on the
// job detail page (PATCH /jobs/{id}/status), not a free-form form field.
export type JobFormData = {
  title: string;
  location: string;
  description: string;
  requiredSkills: string[];
  preferredSkills: string[];
  educationLevel: string;
  experienceMin: number;
  experienceMax: number;
};

interface JobFormProps {
  initialData?: Partial<JobFormData>;
  onSubmit: (data: JobFormData) => void;
  onCancel: () => void;
  isSubmitting?: boolean;
  submitLabel?: string;
}

const defaultData: JobFormData = {
  title: "",
  location: "",
  description: "",
  requiredSkills: [],
  preferredSkills: [],
  educationLevel: "any",
  experienceMin: 0,
  experienceMax: 5,
};

export function JobForm({
  initialData,
  onSubmit,
  onCancel,
  isSubmitting = false,
  submitLabel = "Save Job",
}: JobFormProps) {
  const [formData, setFormData] = React.useState<JobFormData>({
    ...defaultData,
    ...initialData,
  });
  const [skillInput, setSkillInput] = React.useState("");
  const [preferredSkillInput, setPreferredSkillInput] = React.useState("");

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>
  ) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
  };

  const handleSelectChange = (name: string, value: string | null) => {
    setFormData((prev) => ({ ...prev, [name]: value ?? "" }));
  };

  const handleNumberChange = (name: string, value: string) => {
    const numValue = parseInt(value) || 0;
    setFormData((prev) => ({ ...prev, [name]: numValue }));
  };

  const addSkill = (type: "required" | "preferred") => {
    const input = type === "required" ? skillInput : preferredSkillInput;
    const field = type === "required" ? "requiredSkills" : "preferredSkills";

    if (input.trim() && !formData[field].includes(input.trim())) {
      setFormData((prev) => ({
        ...prev,
        [field]: [...prev[field], input.trim()],
      }));
      if (type === "required") {
        setSkillInput("");
      } else {
        setPreferredSkillInput("");
      }
    }
  };

  const removeSkill = (type: "required" | "preferred", skill: string) => {
    const field = type === "required" ? "requiredSkills" : "preferredSkills";
    setFormData((prev) => ({
      ...prev,
      [field]: prev[field].filter((s) => s !== skill),
    }));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit(formData);
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <Card>
        <CardHeader>
          <Typography variant="h5">Basic Information</Typography>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="title">Job Title *</Label>
              <Input
                id="title"
                name="title"
                value={formData.title}
                onChange={handleChange}
                placeholder="e.g. Senior Frontend Developer"
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="location">Location</Label>
              <Input
                id="location"
                name="location"
                value={formData.location}
                onChange={handleChange}
                placeholder="e.g. Remote, New York, NY"
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="description">Job Description *</Label>
            <Textarea
              id="description"
              name="description"
              value={formData.description}
              onChange={handleChange}
              placeholder="Describe the role, responsibilities, and expectations..."
              rows={6}
              required
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <Typography variant="h5">Skills & Requirements</Typography>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label>Required Skills *</Label>
            <div className="flex gap-2">
              <Input
                value={skillInput}
                onChange={(e) => setSkillInput(e.target.value)}
                placeholder="Add a skill and press Enter"
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    addSkill("required");
                  }
                }}
              />
              <Button
                type="button"
                variant="outline"
                onClick={() => addSkill("required")}
              >
                Add
              </Button>
            </div>
            {formData.requiredSkills.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-2">
                {formData.requiredSkills.map((skill) => (
                  <Badge key={skill} variant="default" className="gap-1">
                    {skill}
                    <button
                      type="button"
                      onClick={() => removeSkill("required", skill)}
                      className="hover:bg-primary-foreground/20 rounded-full p-0.5"
                    >
                      <XIcon className="size-3" />
                    </button>
                  </Badge>
                ))}
              </div>
            )}
          </div>

          <div className="space-y-2">
            <Label>Preferred Skills</Label>
            <div className="flex gap-2">
              <Input
                value={preferredSkillInput}
                onChange={(e) => setPreferredSkillInput(e.target.value)}
                placeholder="Add a preferred skill"
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    addSkill("preferred");
                  }
                }}
              />
              <Button
                type="button"
                variant="outline"
                onClick={() => addSkill("preferred")}
              >
                Add
              </Button>
            </div>
            {formData.preferredSkills.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-2">
                {formData.preferredSkills.map((skill) => (
                  <Badge key={skill} variant="secondary" className="gap-1">
                    {skill}
                    <button
                      type="button"
                      onClick={() => removeSkill("preferred", skill)}
                      className="hover:bg-secondary-foreground/20 rounded-full p-0.5"
                    >
                      <XIcon className="size-3" />
                    </button>
                  </Badge>
                ))}
              </div>
            )}
          </div>

          <div className="grid gap-4 sm:grid-cols-3">
            <div className="space-y-2">
              <Label>Education Level</Label>
              <Select
                value={formData.educationLevel}
                onValueChange={(v) => handleSelectChange("educationLevel", v)}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select level" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="high-school">High School</SelectItem>
                  <SelectItem value="associate">Associate Degree</SelectItem>
                  <SelectItem value="bachelors">Bachelor's Degree</SelectItem>
                  <SelectItem value="masters">Master's Degree</SelectItem>
                  <SelectItem value="phd">PhD</SelectItem>
                  <SelectItem value="any">Any</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Min Experience (years)</Label>
              <Input
                type="number"
                min={0}
                value={formData.experienceMin}
                onChange={(e) =>
                  handleNumberChange("experienceMin", e.target.value)
                }
              />
            </div>
            <div className="space-y-2">
              <Label>Max Experience (years)</Label>
              <Input
                type="number"
                min={0}
                value={formData.experienceMax}
                onChange={(e) =>
                  handleNumberChange("experienceMax", e.target.value)
                }
              />
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting ? "Saving..." : submitLabel}
        </Button>
      </div>
    </form>
  );
}
