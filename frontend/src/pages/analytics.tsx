import { useState } from "react";
import { SearchIcon, SparklesIcon } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Typography } from "@/components/ui/typography";

const sampleQueries = [
  "Find React developers with 5+ years experience",
  "Candidates with AWS and Python skills",
  "Show me shortlisted backend engineers",
  "Who has distributed systems experience?",
];

const searchResults = [
  {
    id: "1",
    name: "Emily Davis",
    initials: "ED",
    title: "Senior Frontend Developer",
    matchScore: 95,
    appliedJob: "Senior Frontend Developer",
    skills: ["React", "TypeScript", "Node.js", "GraphQL"],
    experience: "7 years",
    matchingSkills: ["React", "TypeScript"],
  },
  {
    id: "2",
    name: "Sarah Johnson",
    initials: "SJ",
    title: "Frontend Engineer",
    matchScore: 92,
    appliedJob: "Senior Frontend Developer",
    skills: ["React", "Vue.js", "JavaScript", "CSS"],
    experience: "5 years",
    matchingSkills: ["React"],
  },
  {
    id: "3",
    name: "David Brown",
    initials: "DB",
    title: "Full Stack Developer",
    matchScore: 89,
    appliedJob: "Backend Engineer",
    skills: ["React", "Go", "PostgreSQL", "Redis"],
    experience: "6 years",
    matchingSkills: ["React"],
  },
];

export function AnalyticsPage() {
  const [query, setQuery] = useState("");
  const [hasSearched, setHasSearched] = useState(false);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (query.trim()) {
      setHasSearched(true);
    }
  };

  const handleSampleQuery = (sample: string) => {
    setQuery(sample);
    setHasSearched(true);
  };

  return (
    <div className="flex flex-col gap-6">
      <div>
        <Typography variant="h3">AI Analytics</Typography>
        <Typography variant="muted">
          AI-powered search for your talent pipeline
        </Typography>
      </div>

      {/* Search */}
      <Card className="border">
        <CardHeader className="pb-4">
          <Typography variant="h6" className="flex items-center gap-2">
            <SparklesIcon className="text-primary size-4" />
            Semantic Search
          </Typography>
          <Typography variant="muted">
            Use natural language to find candidates
          </Typography>
        </CardHeader>
        <CardContent className="space-y-4">
          <form onSubmit={handleSearch}>
            <div className="relative">
              <SearchIcon className="text-muted-foreground absolute top-1/2 left-3 size-4 -translate-y-1/2" />
              <Input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="e.g., Find candidates with Python and AWS experience"
                className="h-10 pr-20 pl-9"
              />
              <Button
                type="submit"
                size="sm"
                className="absolute top-1/2 right-1 -translate-y-1/2"
              >
                Search
              </Button>
            </div>
          </form>

          {!hasSearched && (
            <div className="space-y-2">
              <Typography variant="muted" className="text-xs">
                Try:
              </Typography>
              <div className="flex flex-wrap gap-2">
                {sampleQueries.map((sample) => (
                  <Button
                    key={sample}
                    variant="outline"
                    size="sm"
                    className="h-7 text-xs"
                    onClick={() => handleSampleQuery(sample)}
                  >
                    {sample}
                  </Button>
                ))}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Results */}
      {hasSearched && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <Typography variant="muted">
              {searchResults.length} candidates found
            </Typography>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setHasSearched(false)}
            >
              Clear
            </Button>
          </div>

          <div className="grid gap-4">
            {searchResults.map((result) => (
              <Card key={result.id} className="border">
                <CardContent className="p-4">
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-3">
                      <div className="bg-muted flex size-10 items-center justify-center text-sm font-medium">
                        {result.initials}
                      </div>
                      <div>
                        <Typography variant="small" className="font-medium">
                          {result.name}
                        </Typography>
                        <Typography variant="muted">
                          {result.title} · {result.experience}
                        </Typography>
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="flex items-center gap-2">
                        <Progress
                          value={result.matchScore}
                          className="h-1.5 w-16"
                        />
                        <Typography variant="small" className="font-medium">
                          {result.matchScore}%
                        </Typography>
                      </div>
                    </div>
                  </div>
                  <div className="mt-4 space-y-3">
                    <div>
                      <Typography variant="muted" className="mb-1 text-xs">
                        Applied for: {result.appliedJob}
                      </Typography>
                      <div className="flex flex-wrap gap-1">
                        {result.skills.map((skill) => (
                          <Badge
                            key={skill}
                            variant={
                              result.matchingSkills.includes(skill)
                                ? "default"
                                : "secondary"
                            }
                            className="text-xs"
                          >
                            {skill}
                          </Badge>
                        ))}
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <Button size="sm">View Resume</Button>
                      <Button variant="outline" size="sm">
                        Shortlist
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
