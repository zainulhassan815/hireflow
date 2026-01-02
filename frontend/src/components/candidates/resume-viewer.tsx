import {
  BriefcaseIcon,
  DownloadIcon,
  GraduationCapIcon,
  MailIcon,
  MapPinIcon,
  PhoneIcon,
  XIcon,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Separator } from "@/components/ui/separator";
import { Typography } from "@/components/ui/typography";

interface Candidate {
  id: string;
  name: string;
  email: string;
  phone?: string;
  location?: string;
  job: string;
  status: string;
  matchScore: number;
  appliedAt: string;
  skills: string[];
  experience?: {
    title: string;
    company: string;
    duration: string;
    description: string;
  }[];
  education?: {
    degree: string;
    institution: string;
    year: string;
  }[];
  summary?: string;
}

interface ResumeViewerProps {
  candidate: Candidate | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onShortlist?: () => void;
  onReject?: () => void;
}

export function ResumeViewer({
  candidate,
  open,
  onOpenChange,
  onShortlist,
  onReject,
}: ResumeViewerProps) {
  if (!candidate) return null;

  // Mock additional data
  const mockExperience = [
    {
      title: "Senior Software Engineer",
      company: "Tech Corp",
      duration: "2020 - Present",
      description:
        "Led development of microservices architecture, mentored junior developers.",
    },
    {
      title: "Software Engineer",
      company: "StartupXYZ",
      duration: "2018 - 2020",
      description: "Full-stack development using React and Node.js.",
    },
  ];

  const mockEducation = [
    {
      degree: "Bachelor of Science in Computer Science",
      institution: "University of Technology",
      year: "2018",
    },
  ];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[85vh] max-w-2xl flex-col overflow-hidden">
        <DialogHeader>
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-4">
              <div className="bg-primary text-primary-foreground flex size-16 items-center justify-center rounded-full text-xl font-semibold">
                {candidate.name
                  .split(" ")
                  .map((n) => n[0])
                  .join("")}
              </div>
              <div>
                <DialogTitle className="text-xl">{candidate.name}</DialogTitle>
                <Typography variant="muted">{candidate.job}</Typography>
                <div className="mt-2 flex items-center gap-2">
                  <Badge
                    variant={
                      candidate.matchScore >= 80 ? "default" : "secondary"
                    }
                    className="font-semibold"
                  >
                    {candidate.matchScore}% Match
                  </Badge>
                  <Badge variant="outline">{candidate.status}</Badge>
                </div>
              </div>
            </div>
          </div>
        </DialogHeader>

        <div className="flex-1 space-y-6 overflow-auto pr-2">
          {/* Contact Info */}
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="flex items-center gap-2 text-sm">
              <MailIcon className="text-muted-foreground size-4" />
              <a
                href={`mailto:${candidate.email}`}
                className="text-primary hover:underline"
              >
                {candidate.email}
              </a>
            </div>
            <div className="flex items-center gap-2 text-sm">
              <PhoneIcon className="text-muted-foreground size-4" />
              <span>+1 (555) 123-4567</span>
            </div>
            <div className="flex items-center gap-2 text-sm">
              <MapPinIcon className="text-muted-foreground size-4" />
              <span>New York, NY</span>
            </div>
          </div>

          <Separator />

          {/* Skills */}
          <div>
            <Typography variant="h6" className="mb-3">
              Skills
            </Typography>
            <div className="flex flex-wrap gap-2">
              {candidate.skills.map((skill) => (
                <Badge key={skill} variant="secondary">
                  {skill}
                </Badge>
              ))}
              {candidate.skills.length < 5 && (
                <>
                  <Badge variant="secondary">Communication</Badge>
                  <Badge variant="secondary">Problem Solving</Badge>
                </>
              )}
            </div>
          </div>

          <Separator />

          {/* Experience */}
          <div>
            <Typography variant="h6" className="mb-3 flex items-center gap-2">
              <BriefcaseIcon className="size-4" />
              Experience
            </Typography>
            <div className="space-y-4">
              {mockExperience.map((exp, idx) => (
                <div key={idx} className="border-muted border-l-2 pl-4">
                  <Typography variant="small" className="font-semibold">
                    {exp.title}
                  </Typography>
                  <Typography variant="muted" className="text-sm">
                    {exp.company} • {exp.duration}
                  </Typography>
                  <Typography variant="small" className="mt-1">
                    {exp.description}
                  </Typography>
                </div>
              ))}
            </div>
          </div>

          <Separator />

          {/* Education */}
          <div>
            <Typography variant="h6" className="mb-3 flex items-center gap-2">
              <GraduationCapIcon className="size-4" />
              Education
            </Typography>
            <div className="space-y-3">
              {mockEducation.map((edu, idx) => (
                <div key={idx}>
                  <Typography variant="small" className="font-semibold">
                    {edu.degree}
                  </Typography>
                  <Typography variant="muted" className="text-sm">
                    {edu.institution} • {edu.year}
                  </Typography>
                </div>
              ))}
            </div>
          </div>

          <Separator />

          {/* Summary */}
          <div>
            <Typography variant="h6" className="mb-3">
              Professional Summary
            </Typography>
            <Typography variant="small" className="text-muted-foreground">
              Experienced software engineer with 5+ years of expertise in
              building scalable web applications. Strong background in React,
              Node.js, and cloud technologies. Passionate about clean code and
              mentoring team members.
            </Typography>
          </div>
        </div>

        <Separator className="my-4" />

        {/* Actions */}
        <div className="flex justify-between gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            <XIcon className="size-4" data-icon="inline-start" />
            Close
          </Button>
          <div className="flex gap-2">
            <Button variant="outline">
              <DownloadIcon className="size-4" data-icon="inline-start" />
              Download Resume
            </Button>
            {candidate.status !== "rejected" && onReject && (
              <Button variant="destructive" onClick={onReject}>
                Reject
              </Button>
            )}
            {candidate.status !== "shortlisted" && onShortlist && (
              <Button onClick={onShortlist}>Shortlist</Button>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
