import * as React from "react";
import {
  DownloadIcon,
  EyeIcon,
  FileIcon,
  FileTextIcon,
  FilterIcon,
  GridIcon,
  ImageIcon,
  ListIcon,
  MoreHorizontalIcon,
  SearchIcon,
  TrashIcon,
  UploadIcon,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Typography } from "@/components/ui/typography";
import { UploadDialog } from "@/components/documents/upload-dialog";
import { DocumentPreview } from "@/components/documents/document-preview";

type DocumentType = "resume" | "report" | "contract" | "letter" | "other";
type ProcessingStatus = "completed" | "processing" | "failed";

interface Document {
  id: string;
  name: string;
  type: DocumentType;
  size: string;
  uploadedAt: string;
  status: ProcessingStatus;
  pages?: number;
  extractedText?: string;
}

const mockDocuments: Document[] = [
  {
    id: "1",
    name: "John_Doe_Resume.pdf",
    type: "resume",
    size: "245 KB",
    uploadedAt: "2024-01-15T10:30:00",
    status: "completed",
    pages: 2,
    extractedText:
      "John Doe\nSoftware Engineer\n5+ years experience in React, Node.js, Python...",
  },
  {
    id: "2",
    name: "Q4_Financial_Report.pdf",
    type: "report",
    size: "1.2 MB",
    uploadedAt: "2024-01-14T14:20:00",
    status: "completed",
    pages: 15,
    extractedText: "Q4 2024 Financial Report\nExecutive Summary...",
  },
  {
    id: "3",
    name: "Employment_Contract_2024.docx",
    type: "contract",
    size: "89 KB",
    uploadedAt: "2024-01-13T09:15:00",
    status: "completed",
    pages: 8,
    extractedText:
      "Employment Agreement\nThis Employment Agreement is entered into...",
  },
  {
    id: "4",
    name: "Sarah_Smith_CV.pdf",
    type: "resume",
    size: "312 KB",
    uploadedAt: "2024-01-12T16:45:00",
    status: "processing",
    pages: 3,
  },
  {
    id: "5",
    name: "Offer_Letter_Template.pdf",
    type: "letter",
    size: "56 KB",
    uploadedAt: "2024-01-11T11:00:00",
    status: "completed",
    pages: 1,
    extractedText:
      "Dear [Candidate Name],\nWe are pleased to offer you the position of...",
  },
  {
    id: "6",
    name: "scanned_document.png",
    type: "other",
    size: "2.1 MB",
    uploadedAt: "2024-01-10T08:30:00",
    status: "failed",
  },
];

const typeConfig: Record<
  DocumentType,
  { label: string; icon: React.ElementType }
> = {
  resume: { label: "Resume", icon: FileTextIcon },
  report: { label: "Report", icon: FileTextIcon },
  contract: { label: "Contract", icon: FileIcon },
  letter: { label: "Letter", icon: FileTextIcon },
  other: { label: "Other", icon: ImageIcon },
};

const statusConfig: Record<
  ProcessingStatus,
  { label: string; variant: "default" | "secondary" | "destructive" }
> = {
  completed: { label: "Completed", variant: "default" },
  processing: { label: "Processing", variant: "secondary" },
  failed: { label: "Failed", variant: "destructive" },
};

export function DocumentsPage() {
  const [view, setView] = React.useState<"list" | "grid">("list");
  const [searchQuery, setSearchQuery] = React.useState("");
  const [typeFilter, setTypeFilter] = React.useState<string>("all");
  const [uploadOpen, setUploadOpen] = React.useState(false);
  const [previewDoc, setPreviewDoc] = React.useState<Document | null>(null);

  const filteredDocuments = mockDocuments.filter((doc) => {
    const matchesSearch = doc.name
      .toLowerCase()
      .includes(searchQuery.toLowerCase());
    const matchesType = typeFilter === "all" || doc.type === typeFilter;
    return matchesSearch && matchesType;
  });

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  };

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <Typography variant="h3">Documents</Typography>
          <Typography variant="muted">
            Upload, manage, and search your documents
          </Typography>
        </div>
        <Button onClick={() => setUploadOpen(true)}>
          <UploadIcon className="size-4" data-icon="inline-start" />
          Upload Documents
        </Button>
      </div>

      {/* Filters and Search */}
      <div className="flex flex-wrap items-center gap-4">
        <div className="relative max-w-sm min-w-[200px] flex-1">
          <SearchIcon className="text-muted-foreground absolute top-1/2 left-3 size-4 -translate-y-1/2" />
          <Input
            placeholder="Search documents..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9"
          />
        </div>
        <Select value={typeFilter} onValueChange={setTypeFilter}>
          <SelectTrigger className="w-[150px]">
            <span className="text-muted-foreground">
              {typeFilter === "all"
                ? "All Types"
                : typeConfig[typeFilter as DocumentType]?.label}
            </span>
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Types</SelectItem>
            <SelectItem value="resume">Resume</SelectItem>
            <SelectItem value="report">Report</SelectItem>
            <SelectItem value="contract">Contract</SelectItem>
            <SelectItem value="letter">Letter</SelectItem>
            <SelectItem value="other">Other</SelectItem>
          </SelectContent>
        </Select>
        <Button variant="outline" size="sm">
          <FilterIcon className="size-4" data-icon="inline-start" />
          More Filters
        </Button>
        <div className="ml-auto flex items-center gap-1">
          <Button
            variant={view === "list" ? "secondary" : "ghost"}
            size="icon-sm"
            onClick={() => setView("list")}
          >
            <ListIcon className="size-4" />
          </Button>
          <Button
            variant={view === "grid" ? "secondary" : "ghost"}
            size="icon-sm"
            onClick={() => setView("grid")}
          >
            <GridIcon className="size-4" />
          </Button>
        </div>
      </div>

      {/* Document Stats */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Card>
          <CardContent className="p-4">
            <Typography variant="muted" className="text-xs">
              Total Documents
            </Typography>
            <Typography variant="h4" className="mt-1">
              {mockDocuments.length}
            </Typography>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <Typography variant="muted" className="text-xs">
              Resumes
            </Typography>
            <Typography variant="h4" className="mt-1">
              {mockDocuments.filter((d) => d.type === "resume").length}
            </Typography>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <Typography variant="muted" className="text-xs">
              Processing
            </Typography>
            <Typography variant="h4" className="mt-1">
              {mockDocuments.filter((d) => d.status === "processing").length}
            </Typography>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <Typography variant="muted" className="text-xs">
              Failed
            </Typography>
            <Typography variant="h4" className="mt-1">
              {mockDocuments.filter((d) => d.status === "failed").length}
            </Typography>
          </CardContent>
        </Card>
      </div>

      {/* Documents List/Grid */}
      {view === "list" ? (
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Size</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Uploaded</TableHead>
                <TableHead className="w-10"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredDocuments.map((doc) => {
                const TypeIcon = typeConfig[doc.type].icon;
                return (
                  <TableRow key={doc.id}>
                    <TableCell>
                      <div className="flex items-center gap-3">
                        <div className="bg-muted flex size-8 items-center justify-center rounded">
                          <TypeIcon className="text-muted-foreground size-4" />
                        </div>
                        <div>
                          <Typography variant="small" className="font-medium">
                            {doc.name}
                          </Typography>
                          {doc.pages && (
                            <Typography variant="muted" className="text-xs">
                              {doc.pages} page{doc.pages > 1 ? "s" : ""}
                            </Typography>
                          )}
                        </div>
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">
                        {typeConfig[doc.type].label}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Typography variant="small">{doc.size}</Typography>
                    </TableCell>
                    <TableCell>
                      {doc.status === "processing" ? (
                        <div className="flex items-center gap-2">
                          <Progress value={65} className="h-1.5 w-16" />
                          <Typography variant="muted" className="text-xs">
                            65%
                          </Typography>
                        </div>
                      ) : (
                        <Badge variant={statusConfig[doc.status].variant}>
                          {statusConfig[doc.status].label}
                        </Badge>
                      )}
                    </TableCell>
                    <TableCell>
                      <Typography variant="muted">
                        {formatDate(doc.uploadedAt)}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon-sm">
                            <MoreHorizontalIcon className="size-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem onClick={() => setPreviewDoc(doc)}>
                            <EyeIcon className="mr-2 size-4" />
                            Preview
                          </DropdownMenuItem>
                          <DropdownMenuItem>
                            <DownloadIcon className="mr-2 size-4" />
                            Download
                          </DropdownMenuItem>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem className="text-destructive">
                            <TrashIcon className="mr-2 size-4" />
                            Delete
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {filteredDocuments.map((doc) => {
            const TypeIcon = typeConfig[doc.type].icon;
            return (
              <Card
                key={doc.id}
                className="cursor-pointer transition-shadow hover:shadow-md"
              >
                <CardContent className="p-4">
                  <div className="flex items-start justify-between">
                    <div className="bg-muted flex size-12 items-center justify-center rounded">
                      <TypeIcon className="text-muted-foreground size-6" />
                    </div>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="icon-sm">
                          <MoreHorizontalIcon className="size-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onClick={() => setPreviewDoc(doc)}>
                          <EyeIcon className="mr-2 size-4" />
                          Preview
                        </DropdownMenuItem>
                        <DropdownMenuItem>
                          <DownloadIcon className="mr-2 size-4" />
                          Download
                        </DropdownMenuItem>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem className="text-destructive">
                          <TrashIcon className="mr-2 size-4" />
                          Delete
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div>
                  <div className="mt-4">
                    <Typography
                      variant="small"
                      className="line-clamp-1 font-medium"
                    >
                      {doc.name}
                    </Typography>
                    <div className="mt-2 flex items-center gap-2">
                      <Badge variant="outline" className="text-xs">
                        {typeConfig[doc.type].label}
                      </Badge>
                      <Typography variant="muted" className="text-xs">
                        {doc.size}
                      </Typography>
                    </div>
                    <div className="mt-3">
                      {doc.status === "processing" ? (
                        <div className="flex items-center gap-2">
                          <Progress value={65} className="h-1.5 flex-1" />
                          <Typography variant="muted" className="text-xs">
                            65%
                          </Typography>
                        </div>
                      ) : (
                        <Badge variant={statusConfig[doc.status].variant}>
                          {statusConfig[doc.status].label}
                        </Badge>
                      )}
                    </div>
                    <Typography variant="muted" className="mt-2 text-xs">
                      {formatDate(doc.uploadedAt)}
                    </Typography>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      {/* Modals */}
      <UploadDialog open={uploadOpen} onOpenChange={setUploadOpen} />
      <DocumentPreview
        document={previewDoc}
        open={!!previewDoc}
        onOpenChange={(open) => !open && setPreviewDoc(null)}
      />
    </div>
  );
}
