# Product Requirements Document (PRD)

## AI-Powered HR Screening and Document Retrieval System Using RAG

**Version:** 1.0
**Date:** December 21, 2025
**Authors:** Amna Ikram, Zain Ul Hassan, Ezza Ansar
**Institution:** Sharif College of Engineering & Technology

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Problem Statement](#2-problem-statement)
3. [Goals and Objectives](#3-goals-and-objectives)
4. [Target Users](#4-target-users)
5. [User Stories](#5-user-stories)
6. [Functional Requirements](#6-functional-requirements)
7. [Non-Functional Requirements](#7-non-functional-requirements)
8. [System Architecture](#8-system-architecture)
9. [Data Models](#9-data-models)
10. [API Specifications](#10-api-specifications)
11. [UI/UX Requirements](#11-uiux-requirements)
12. [Technical Stack](#12-technical-stack)
13. [Security Requirements](#13-security-requirements)
14. [Implementation Phases](#14-implementation-phases)
15. [Success Metrics](#15-success-metrics)
16. [Risks and Mitigations](#16-risks-and-mitigations)
17. [Glossary](#17-glossary)

---

## 1. Executive Summary

### 1.1 Product Vision

The AI-Powered HR Screening and Document Retrieval System is an intelligent document processing platform that leverages Retrieval-Augmented Generation (RAG) technology to automate HR resume screening and provide semantic document search capabilities. The system aims to reduce manual effort in document review by up to 70% while improving accuracy and consistency in candidate evaluation.

### 1.2 Key Value Propositions

| Value                          | Description                                                |
| ------------------------------ | ---------------------------------------------------------- |
| **Automated Resume Screening** | AI-powered matching of candidates against job requirements |
| **Semantic Search**            | Natural language queries instead of keyword matching       |
| **Intelligent Q&A**            | Context-aware answers from document collections            |
| **Email Integration**          | Automated resume collection from Gmail                     |
| **Time Savings**               | Reduce screening time from hours to minutes                |

### 1.3 Scope

**In Scope:**

- Document upload, processing, and OCR
- Semantic search with vector embeddings
- RAG-based question answering
- HR resume screening and candidate management
- Gmail integration for resume collection
- Job posting management
- Export functionality (Excel)
- Activity logging and audit trails

**Out of Scope (v1.0):**

- Third-party ATS integration
- Video/audio file processing
- Mobile applications (iOS/Android)
- Multi-language support (beyond English)

---

## 2. Problem Statement

### 2.1 Current Challenges

Organizations face significant challenges in document management and HR recruitment:

1. **Manual Document Review**: HR teams spend 60-70% of their time manually reviewing resumes
2. **Inconsistent Evaluation**: Different reviewers apply different criteria leading to bias
3. **Information Retrieval**: Finding specific information in large document collections is time-consuming
4. **Scalability Issues**: Manual processes don't scale with increasing application volumes
5. **Data Silos**: Documents scattered across emails, folders, and systems

### 2.2 Impact

| Problem               | Business Impact                       |
| --------------------- | ------------------------------------- |
| Manual screening      | 23 hours average to fill one position |
| Missed candidates     | Top talent lost to competitors        |
| Inconsistent criteria | Legal and compliance risks            |
| Slow retrieval        | Delayed decision-making               |

### 2.3 Solution

An AI-powered system that:

- Automatically processes and indexes documents
- Enables semantic search using natural language
- Matches candidates against job requirements using AI
- Provides instant answers from document collections
- Integrates with email for automated document collection

---

## 3. Goals and Objectives

### 3.1 Primary Goals

| Goal   | Description                        | Success Criteria                       |
| ------ | ---------------------------------- | -------------------------------------- |
| **G1** | Automate resume screening          | 80% reduction in manual screening time |
| **G2** | Enable intelligent document search | Search results in < 2 seconds          |
| **G3** | Provide accurate Q&A               | 85% relevance score on answers         |
| **G4** | Streamline HR workflow             | End-to-end candidate processing        |

### 3.2 Objectives

1. **O1**: Process documents (PDF, DOCX, images) with OCR accuracy > 95%
2. **O2**: Index documents using vector embeddings for semantic search
3. **O3**: Match candidates against job descriptions with relevance scoring
4. **O4**: Integrate with Gmail for automated resume collection
5. **O5**: Provide exportable reports in Excel format
6. **O6**: Maintain audit trails for compliance

### 3.3 Key Results

- Process 100+ resumes per hour
- Support 100,000+ documents in the system
- Achieve < 10 second response time for RAG queries
- 99.5% system uptime

---

## 4. Target Users

### 4.1 User Personas

#### Persona 1: HR Recruiter (Primary User)

```
Name: Sarah Ahmed
Role: HR Recruiter
Age: 28
Technical Skills: Moderate
Daily Tasks:
  - Review 50-100 resumes daily
  - Screen candidates against job requirements
  - Schedule interviews
  - Communicate with candidates

Pain Points:
  - Overwhelmed by resume volume
  - Inconsistent screening criteria
  - Time spent on repetitive tasks
  - Missing qualified candidates

Goals:
  - Faster candidate screening
  - Better quality shortlists
  - More time for interviews
  - Consistent evaluation criteria
```

#### Persona 2: HR Manager (Secondary User)

```
Name: Ahmed Khan
Role: HR Manager
Age: 42
Technical Skills: Basic to Moderate
Daily Tasks:
  - Oversee recruitment process
  - Define job requirements
  - Review shortlisted candidates
  - Make hiring decisions

Pain Points:
  - Lack of visibility into screening process
  - Inconsistent candidate quality
  - Compliance concerns
  - Reporting overhead

Goals:
  - Better oversight of recruitment
  - Consistent hiring standards
  - Compliance and audit trails
  - Easy reporting and analytics
```

#### Persona 3: System Administrator (Technical User)

```
Name: Ali Hassan
Role: IT Administrator
Age: 35
Technical Skills: Advanced
Daily Tasks:
  - System maintenance
  - User management
  - Security monitoring
  - Integration management

Pain Points:
  - System reliability
  - Security concerns
  - Integration complexity
  - Performance monitoring

Goals:
  - Stable system operation
  - Secure data handling
  - Easy maintenance
  - Clear documentation
```

### 4.2 User Access Levels

| Role          | Access Level | Capabilities                                  |
| ------------- | ------------ | --------------------------------------------- |
| HR Personnel  | Standard     | Full HR module, document search, Q&A          |
| HR Manager    | Elevated     | Standard + reporting, job management          |
| Administrator | Full         | All features + user management, system config |

---

## 5. User Stories

### 5.1 Authentication & Access

| ID     | User Story                                                                                            | Priority    | Acceptance Criteria                                                                                                                 |
| ------ | ----------------------------------------------------------------------------------------------------- | ----------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| US-001 | As an HR user, I want to log in with my email and password so that I can access the system securely   | Must Have   | - Login form with email/password<br>- Validation of credentials<br>- Redirect to dashboard on success<br>- Error message on failure |
| US-002 | As a user, I want to reset my password so that I can regain access if I forget it                     | Must Have   | - "Forgot password" link<br>- Email verification<br>- Secure password reset flow<br>- Confirmation message                          |
| US-003 | As a user, I want to stay logged in for my session so that I don't have to re-authenticate repeatedly | Should Have | - JWT token-based session<br>- 24-hour session duration<br>- Automatic logout on inactivity                                         |

### 5.2 Document Management

| ID     | User Story                                                                                                  | Priority    | Acceptance Criteria                                                                                                                 |
| ------ | ----------------------------------------------------------------------------------------------------------- | ----------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| US-010 | As an HR user, I want to upload documents (PDF, DOCX, images) so that they can be processed and indexed     | Must Have   | - Drag-and-drop upload<br>- Multiple file selection<br>- Progress indicator<br>- Success/error feedback                             |
| US-011 | As an HR user, I want documents to be automatically processed with OCR so that text is extracted for search | Must Have   | - Automatic OCR on upload<br>- Text extraction from images<br>- Processing status indicator<br>- Error handling for corrupted files |
| US-012 | As an HR user, I want to view all uploaded documents in a dashboard so that I can manage them easily        | Must Have   | - Document list view<br>- Sorting by date, name, type<br>- Pagination<br>- Document preview                                         |
| US-013 | As an HR user, I want to delete documents so that I can remove outdated or incorrect files                  | Should Have | - Delete button per document<br>- Confirmation dialog<br>- Soft delete with recovery option                                         |

### 5.3 Search & Retrieval

| ID     | User Story                                                                                                                    | Priority    | Acceptance Criteria                                                                                                |
| ------ | ----------------------------------------------------------------------------------------------------------------------------- | ----------- | ------------------------------------------------------------------------------------------------------------------ |
| US-020 | As an HR user, I want to search documents using natural language so that I can find information without exact keywords        | Must Have   | - Search input field<br>- Semantic search results<br>- Relevance ranking<br>- Results in < 2 seconds               |
| US-021 | As an HR user, I want to filter search results by document type, date, and metadata so that I can narrow down results         | Should Have | - Filter panel<br>- Multiple filter options<br>- Clear filters option<br>- Real-time filtering                     |
| US-022 | As an HR user, I want to see highlighted matches in search results so that I can quickly identify relevant content            | Should Have | - Text highlighting<br>- Context snippets<br>- Click to view full document                                         |
| US-023 | As an HR user, I want to ask questions about documents and get AI-generated answers so that I can quickly extract information | Must Have   | - Chat-style Q&A interface<br>- Context-aware answers<br>- Source document citations<br>- Response in < 10 seconds |

### 5.4 Job Management

| ID     | User Story                                                                                                                    | Priority    | Acceptance Criteria                                                                                              |
| ------ | ----------------------------------------------------------------------------------------------------------------------------- | ----------- | ---------------------------------------------------------------------------------------------------------------- |
| US-030 | As an HR user, I want to create job postings with required skills and criteria so that candidates can be matched against them | Must Have   | - Job creation form<br>- Fields: title, description, skills, experience, education<br>- Save and publish options |
| US-031 | As an HR user, I want to edit existing job postings so that I can update requirements                                         | Must Have   | - Edit form pre-populated<br>- Save changes<br>- Version history                                                 |
| US-032 | As an HR user, I want to delete job postings so that I can remove filled or cancelled positions                               | Should Have | - Delete with confirmation<br>- Archive option<br>- Associated resumes handling                                  |
| US-033 | As an HR user, I want to view all job postings in a list so that I can manage them                                            | Must Have   | - Job list view<br>- Status indicators (active/closed)<br>- Candidate count per job                              |

### 5.5 Resume Screening

| ID     | User Story                                                                                          | Priority  | Acceptance Criteria                                                                                                    |
| ------ | --------------------------------------------------------------------------------------------------- | --------- | ---------------------------------------------------------------------------------------------------------------------- |
| US-040 | As an HR user, I want to view parsed resume content so that I can review candidate information      | Must Have | - Structured resume view<br>- Extracted fields: name, email, skills, experience, education<br>- Original document link |
| US-041 | As an HR user, I want to see AI-ranked candidates for a job so that I can focus on the best matches | Must Have | - Ranked candidate list<br>- Match score percentage<br>- Skill match breakdown<br>- Experience relevance               |
| US-042 | As an HR user, I want to shortlist candidates so that I can track selected applicants               | Must Have | - Shortlist button<br>- Shortlist status indicator<br>- Shortlisted candidates view                                    |
| US-043 | As an HR user, I want to reject candidates so that I can track decisions                            | Must Have | - Reject button<br>- Optional rejection reason<br>- Rejected candidates view                                           |
| US-044 | As an HR user, I want to export shortlisted candidates to Excel so that I can share and report      | Must Have | - Export button<br>- Excel file download<br>- Configurable columns<br>- All candidate data included                    |

### 5.6 Email Integration

| ID     | User Story                                                                                                                      | Priority    | Acceptance Criteria                                                                                          |
| ------ | ------------------------------------------------------------------------------------------------------------------------------- | ----------- | ------------------------------------------------------------------------------------------------------------ |
| US-050 | As an HR user, I want to connect my Gmail account so that resumes can be automatically collected                                | Must Have   | - OAuth 2.0 authentication<br>- Secure token storage<br>- Connection status indicator<br>- Disconnect option |
| US-051 | As an HR user, I want the system to automatically sync resume attachments from my email so that I don't have to manually upload | Must Have   | - Automatic sync on schedule<br>- Manual sync trigger<br>- Sync status and history<br>- Duplicate detection  |
| US-052 | As an HR user, I want to send emails to candidates so that I can communicate interview invitations or updates                   | Should Have | - Email composer<br>- Template support<br>- Attachment option<br>- Sent email log                            |

### 5.7 Logs & Administration

| ID     | User Story                                                                               | Priority    | Acceptance Criteria                                                                          |
| ------ | ---------------------------------------------------------------------------------------- | ----------- | -------------------------------------------------------------------------------------------- |
| US-060 | As an HR user, I want to view system activity logs so that I can track actions and audit | Should Have | - Log list view<br>- Filter by date, action type, user<br>- Export logs                      |
| US-061 | As an HR user, I want to view document metadata so that I can see extracted information  | Should Have | - Metadata panel<br>- Fields: type, date, author, skills, entities<br>- Edit metadata option |

---

## 6. Functional Requirements

### 6.1 Authentication Module

#### FR-AUTH-001: User Registration

```
Description: System shall allow new user registration
Input: Email, Password, Name, Role
Process:
  1. Validate email format and uniqueness
  2. Enforce password policy (min 8 chars, 1 uppercase, 1 number, 1 special)
  3. Hash password using bcrypt
  4. Store user in database
  5. Send verification email
Output: Success message or validation errors
```

#### FR-AUTH-002: User Login

```
Description: System shall authenticate users with email and password
Input: Email, Password
Process:
  1. Validate credentials against database
  2. Generate JWT access token (expires: 1 hour)
  3. Generate refresh token (expires: 7 days)
  4. Log login activity
Output: JWT tokens and user profile
```

#### FR-AUTH-003: Password Reset

```
Description: System shall allow password reset via email
Input: Email address
Process:
  1. Verify email exists in system
  2. Generate secure reset token (expires: 1 hour)
  3. Send reset link via email
  4. Validate token on reset page
  5. Update password and invalidate token
Output: Success/error message
```

### 6.2 Document Processing Module

#### FR-DOC-001: Document Upload

```
Description: System shall accept document uploads
Supported Formats: PDF, DOCX, DOC, PNG, JPG, JPEG, TIFF
Max File Size: 25 MB per file
Max Batch Size: 50 files
Process:
  1. Validate file type and size
  2. Generate unique document ID
  3. Store file in secure storage
  4. Queue for processing
  5. Return upload status
Output: Document ID, upload status, processing queue position
```

#### FR-DOC-002: Text Extraction

```
Description: System shall extract text from uploaded documents
Process:
  1. Detect document type
  2. For PDF: Use PyMuPDF for text extraction
  3. For Images: Use Tesseract OCR
  4. For DOCX: Use python-docx
  5. Clean and normalize extracted text
  6. Store extracted text in database
Output: Extracted text, OCR confidence score, processing time
```

#### FR-DOC-003: Document Classification

```
Description: System shall automatically classify document type
Categories: Resume, Report, Contract, Letter, Other
Process:
  1. Analyze extracted text
  2. Use ML classifier to determine type
  3. Extract type-specific metadata
  4. Tag document with classification
Output: Document type, confidence score, extracted metadata
```

#### FR-DOC-004: Vector Embedding Generation

```
Description: System shall generate vector embeddings for semantic search
Process:
  1. Chunk document text (500 tokens, 50 token overlap)
  2. Generate embeddings using sentence-transformers
  3. Store embeddings in vector database
  4. Index for similarity search
Output: Embedding vectors, chunk IDs, index status
```

### 6.3 Search Module

#### FR-SEARCH-001: Semantic Search

```
Description: System shall perform semantic search on documents
Input: Natural language query
Process:
  1. Generate query embedding
  2. Perform similarity search in vector database
  3. Retrieve top-k matching chunks (default k=10)
  4. Aggregate results by document
  5. Rank by relevance score
Output: Ranked document list with relevance scores and snippets
```

#### FR-SEARCH-002: Filtered Search

```
Description: System shall support filtered search
Filter Options:
  - Document type (resume, report, etc.)
  - Date range (uploaded, created)
  - Skills (for resumes)
  - Job role
  - Custom metadata
Process:
  1. Apply metadata filters to document set
  2. Perform semantic search on filtered set
  3. Return filtered and ranked results
Output: Filtered search results
```

#### FR-SEARCH-003: RAG Question Answering

```
Description: System shall answer questions using RAG
Input: Natural language question
Process:
  1. Generate question embedding
  2. Retrieve relevant document chunks (top-5)
  3. Construct prompt with context
  4. Generate answer using LLM
  5. Include source citations
Output: AI-generated answer with source documents
```

### 6.4 HR Screening Module

#### FR-HR-001: Job Creation

```
Description: System shall allow creation of job postings
Input:
  - Job Title (required)
  - Description (required)
  - Required Skills (required, list)
  - Preferred Skills (optional, list)
  - Education Level (required)
  - Experience Years (required, min/max)
  - Location (optional)
  - Salary Range (optional)
Process:
  1. Validate required fields
  2. Generate job ID
  3. Store job posting
  4. Create skill embeddings for matching
Output: Job ID, creation status
```

#### FR-HR-002: Resume Parsing

```
Description: System shall extract structured data from resumes
Extracted Fields:
  - Full Name
  - Email Address
  - Phone Number
  - LinkedIn URL
  - Skills (list)
  - Education (institution, degree, year)
  - Experience (company, role, duration, description)
  - Certifications
  - Languages
Process:
  1. Use NLP to identify sections
  2. Extract entities using NER
  3. Parse structured data
  4. Validate and clean data
  5. Store parsed resume
Output: Structured candidate profile
```

#### FR-HR-003: Candidate Matching

```
Description: System shall match candidates to jobs
Input: Job ID, Candidate IDs (or all)
Process:
  1. Load job requirements
  2. For each candidate:
     a. Compare skills (semantic similarity)
     b. Check education requirements
     c. Evaluate experience match
     d. Calculate overall match score
  3. Rank candidates by score
Output: Ranked candidate list with match scores and breakdown
```

#### FR-HR-004: Candidate Status Management

```
Description: System shall track candidate status
Statuses: New, Reviewed, Shortlisted, Rejected, Interviewed, Hired
Process:
  1. Update candidate status
  2. Log status change with timestamp and user
  3. Trigger notifications if configured
Output: Updated status, audit log entry
```

### 6.5 Email Integration Module

#### FR-EMAIL-001: Gmail OAuth Connection

```
Description: System shall connect to Gmail via OAuth 2.0
Scopes Required:
  - gmail.readonly (read emails)
  - gmail.send (send emails)
  - gmail.modify (mark as read)
Process:
  1. Initiate OAuth flow
  2. User grants permissions
  3. Store encrypted refresh token
  4. Verify connection
Output: Connection status, connected email address
```

#### FR-EMAIL-002: Resume Sync

```
Description: System shall sync resume attachments from email
Process:
  1. Query emails with attachments
  2. Filter by supported file types
  3. Download attachments
  4. Check for duplicates (hash-based)
  5. Queue new resumes for processing
  6. Mark emails as processed
Output: Sync summary (new resumes, duplicates, errors)
```

#### FR-EMAIL-003: Send Email

```
Description: System shall send emails to candidates
Input: Recipient, Subject, Body, Attachments (optional)
Process:
  1. Validate recipient email
  2. Construct email message
  3. Add attachments if any
  4. Send via Gmail API
  5. Log sent email
Output: Send status, message ID
```

### 6.6 Export Module

#### FR-EXPORT-001: Excel Export

```
Description: System shall export data to Excel format
Export Types:
  - Search results
  - Shortlisted candidates
  - All candidates for a job
  - Activity logs
Process:
  1. Gather data based on export type
  2. Apply user-selected columns
  3. Generate Excel file using openpyxl
  4. Return downloadable file
Output: Excel file (.xlsx)
```

---

## 7. Non-Functional Requirements

### 7.1 Performance Requirements

| ID           | Requirement              | Target       | Measurement                      |
| ------------ | ------------------------ | ------------ | -------------------------------- |
| NFR-PERF-001 | Document upload response | < 3 seconds  | Time from upload to confirmation |
| NFR-PERF-002 | OCR processing time      | < 30 seconds | Per standard document            |
| NFR-PERF-003 | Search query response    | < 2 seconds  | From query to results            |
| NFR-PERF-004 | RAG Q&A response         | < 10 seconds | From question to answer          |
| NFR-PERF-005 | Page load time           | < 2 seconds  | Initial page render              |
| NFR-PERF-006 | Concurrent users         | 50+ users    | Without degradation              |
| NFR-PERF-007 | Document capacity        | 100,000+     | Total indexed documents          |

### 7.2 Scalability Requirements

| ID            | Requirement        | Description                                   |
| ------------- | ------------------ | --------------------------------------------- |
| NFR-SCALE-001 | Horizontal scaling | System shall support adding more worker nodes |
| NFR-SCALE-002 | Database scaling   | Support read replicas for query scaling       |
| NFR-SCALE-003 | Storage scaling    | Support expandable document storage           |
| NFR-SCALE-004 | Queue scaling      | Support distributed task queues               |

### 7.3 Availability Requirements

| ID            | Requirement                    | Target          |
| ------------- | ------------------------------ | --------------- |
| NFR-AVAIL-001 | System uptime                  | 99.5%           |
| NFR-AVAIL-002 | Planned maintenance window     | < 4 hours/month |
| NFR-AVAIL-003 | Recovery time objective (RTO)  | < 4 hours       |
| NFR-AVAIL-004 | Recovery point objective (RPO) | < 1 hour        |

### 7.4 Security Requirements

| ID          | Requirement                | Description                        |
| ----------- | -------------------------- | ---------------------------------- |
| NFR-SEC-001 | Data encryption at rest    | AES-256 encryption for stored data |
| NFR-SEC-002 | Data encryption in transit | TLS 1.3 for all communications     |
| NFR-SEC-003 | Password storage           | bcrypt with salt (cost factor 12)  |
| NFR-SEC-004 | Session management         | JWT with secure httpOnly cookies   |
| NFR-SEC-005 | Input validation           | Sanitize all user inputs           |
| NFR-SEC-006 | SQL injection prevention   | Parameterized queries only         |
| NFR-SEC-007 | XSS prevention             | Content Security Policy headers    |
| NFR-SEC-008 | Rate limiting              | 100 requests/minute per user       |

### 7.5 Usability Requirements

| ID          | Requirement       | Description                                   |
| ----------- | ----------------- | --------------------------------------------- |
| NFR-USE-001 | Browser support   | Chrome 90+, Firefox 88+, Edge 90+, Safari 14+ |
| NFR-USE-002 | Responsive design | Support 1024px to 1920px widths               |
| NFR-USE-003 | Accessibility     | WCAG 2.1 Level AA compliance                  |
| NFR-USE-004 | Error messages    | Clear, actionable error messages              |
| NFR-USE-005 | Loading states    | Visual feedback for all async operations      |

### 7.6 Maintainability Requirements

| ID            | Requirement        | Description                             |
| ------------- | ------------------ | --------------------------------------- |
| NFR-MAINT-001 | Code documentation | All modules documented with docstrings  |
| NFR-MAINT-002 | API documentation  | OpenAPI/Swagger specification           |
| NFR-MAINT-003 | Logging            | Structured logging with correlation IDs |
| NFR-MAINT-004 | Monitoring         | Health checks and metrics endpoints     |
| NFR-MAINT-005 | Test coverage      | Minimum 80% code coverage               |

---

## 8. System Architecture

### 8.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CLIENT LAYER                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                     React.js Frontend Application                     │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │   │
│  │  │  Auth    │ │ Document │ │  Search  │ │    HR    │ │  Admin   │  │   │
│  │  │  Module  │ │  Module  │ │  Module  │ │  Module  │ │  Module  │  │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      │ HTTPS/REST API
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              API GATEWAY                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    FastAPI Backend Application                        │   │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐                 │   │
│  │  │ Auth Router  │ │ Doc Router   │ │Search Router │                 │   │
│  │  └──────────────┘ └──────────────┘ └──────────────┘                 │   │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐                 │   │
│  │  │  HR Router   │ │Email Router  │ │Admin Router  │                 │   │
│  │  └──────────────┘ └──────────────┘ └──────────────┘                 │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                    ┌─────────────────┼─────────────────┐
                    ▼                 ▼                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            SERVICE LAYER                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐       │
│  │  Document    │ │   Search     │ │     HR       │ │    Email     │       │
│  │  Service     │ │   Service    │ │   Service    │ │   Service    │       │
│  └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘       │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐                        │
│  │    OCR       │ │  Embedding   │ │     RAG      │                        │
│  │  Service     │ │   Service    │ │   Service    │                        │
│  └──────────────┘ └──────────────┘ └──────────────┘                        │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                    ┌─────────────────┼─────────────────┐
                    ▼                 ▼                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                             DATA LAYER                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐       │
│  │ PostgreSQL   │ │   ChromaDB   │ │    Redis     │ │    MinIO     │       │
│  │  (Metadata)  │ │  (Vectors)   │ │   (Cache)    │ │   (Files)    │       │
│  └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘       │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          BACKGROUND WORKERS                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐       │
│  │   Celery     │ │    OCR       │ │  Embedding   │ │    Email     │       │
│  │   Worker     │ │   Worker     │ │   Worker     │ │    Sync      │       │
│  └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘       │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 8.2 Component Description

| Component         | Technology            | Purpose                           |
| ----------------- | --------------------- | --------------------------------- |
| Frontend          | React.js + TypeScript | User interface                    |
| API Gateway       | FastAPI               | REST API endpoints                |
| Document Service  | Python                | Document processing orchestration |
| OCR Service       | Tesseract + PyMuPDF   | Text extraction                   |
| Embedding Service | Sentence-Transformers | Vector generation                 |
| Search Service    | ChromaDB              | Semantic search                   |
| RAG Service       | LangChain + LLM       | Question answering                |
| HR Service        | Python                | Resume parsing and matching       |
| Email Service     | Gmail API             | Email integration                 |
| PostgreSQL        | PostgreSQL 15         | Relational data storage           |
| ChromaDB          | ChromaDB              | Vector storage                    |
| Redis             | Redis 7               | Caching and sessions              |
| MinIO             | MinIO                 | Object/file storage               |
| Celery            | Celery + Redis        | Background task processing        |

### 8.3 Data Flow Diagrams

#### Document Upload Flow

```
User                Frontend            API              Service           Database
 │                    │                  │                  │                  │
 │──Upload File──────>│                  │                  │                  │
 │                    │──POST /docs──────>│                 │                  │
 │                    │                  │──Validate───────>│                  │
 │                    │                  │                  │──Store File─────>│
 │                    │                  │                  │<─File ID─────────│
 │                    │                  │──Queue Task─────>│                  │
 │                    │<─202 Accepted────│                  │                  │
 │<─Upload Started────│                  │                  │                  │
 │                    │                  │                  │                  │
 │                    │        [Background Processing]      │                  │
 │                    │                  │                  │                  │
 │                    │                  │      Worker──────│──OCR Extract────>│
 │                    │                  │                  │──Gen Embedding──>│
 │                    │                  │                  │──Update Status──>│
 │                    │                  │                  │                  │
 │                    │<─WebSocket: Done─│                  │                  │
 │<─Processing Done───│                  │                  │                  │
```

#### Search Flow

```
User                Frontend            API              Search            Vector DB
 │                    │                  │                  │                  │
 │──Enter Query──────>│                  │                  │                  │
 │                    │──GET /search─────>│                 │                  │
 │                    │                  │──Search Request─>│                  │
 │                    │                  │                  │──Query Embed────>│
 │                    │                  │                  │<─Similar Chunks──│
 │                    │                  │<─Ranked Results──│                  │
 │                    │<─200 Results─────│                  │                  │
 │<─Display Results───│                  │                  │                  │
```

#### RAG Q&A Flow

```
User                Frontend            API               RAG             LLM
 │                    │                  │                  │               │
 │──Ask Question─────>│                  │                  │               │
 │                    │──POST /qa────────>│                 │               │
 │                    │                  │──QA Request─────>│               │
 │                    │                  │                  │──Get Context──│
 │                    │                  │                  │<─Chunks───────│
 │                    │                  │                  │──Prompt+Ctx──>│
 │                    │                  │                  │<─Answer───────│
 │                    │                  │<─Answer+Sources──│               │
 │                    │<─200 Answer──────│                  │               │
 │<─Display Answer────│                  │                  │               │
```

---

## 9. Data Models

### 9.1 Entity Relationship Diagram

```
┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐
│      User       │       │    Document     │       │      Job        │
├─────────────────┤       ├─────────────────┤       ├─────────────────┤
│ id (PK)         │       │ id (PK)         │       │ id (PK)         │
│ email           │──┐    │ user_id (FK)    │   ┌───│ user_id (FK)    │
│ password_hash   │  │    │ filename        │   │   │ title           │
│ name            │  │    │ file_type       │   │   │ description     │
│ role            │  │    │ file_path       │   │   │ required_skills │
│ created_at      │  │    │ file_size       │   │   │ preferred_skills│
│ updated_at      │  │    │ extracted_text  │   │   │ education_level │
│ last_login      │  │    │ doc_type        │   │   │ experience_min  │
│ is_active       │  │    │ status          │   │   │ experience_max  │
└─────────────────┘  │    │ ocr_confidence  │   │   │ location        │
                     │    │ created_at      │   │   │ status          │
                     └────│ updated_at      │   │   │ created_at      │
                          └─────────────────┘   │   │ updated_at      │
                                   │            │   └─────────────────┘
                                   │            │            │
                          ┌────────┴────────┐   │            │
                          ▼                 ▼   │            │
                ┌─────────────────┐  ┌──────────┴──┐  ┌──────┴────────┐
                │  DocumentChunk  │  │   Resume    │  │  Application  │
                ├─────────────────┤  ├─────────────┤  ├───────────────┤
                │ id (PK)         │  │ id (PK)     │  │ id (PK)       │
                │ document_id(FK) │  │ document_id │  │ job_id (FK)   │
                │ chunk_index     │  │ candidate..│  │ resume_id(FK) │
                │ content         │  │ email       │  │ match_score   │
                │ embedding_id    │  │ phone       │  │ status        │
                │ start_pos       │  │ skills      │  │ created_at    │
                │ end_pos         │  │ education   │  │ updated_at    │
                └─────────────────┘  │ experience  │  └───────────────┘
                                     │ parsed_data │
                                     │ created_at  │
                                     └─────────────┘

┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐
│  EmailAccount   │       │   SyncHistory   │       │   ActivityLog   │
├─────────────────┤       ├─────────────────┤       ├─────────────────┤
│ id (PK)         │       │ id (PK)         │       │ id (PK)         │
│ user_id (FK)    │───────│ account_id (FK) │       │ user_id (FK)    │
│ email_address   │       │ sync_type       │       │ action          │
│ refresh_token   │       │ started_at      │       │ entity_type     │
│ access_token    │       │ completed_at    │       │ entity_id       │
│ token_expiry    │       │ status          │       │ details         │
│ is_connected    │       │ items_processed │       │ ip_address      │
│ created_at      │       │ errors          │       │ created_at      │
└─────────────────┘       └─────────────────┘       └─────────────────┘
```

### 9.2 Database Schema

#### Users Table

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL DEFAULT 'hr_user',
    is_active BOOLEAN DEFAULT TRUE,
    email_verified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP WITH TIME ZONE,

    CONSTRAINT valid_role CHECK (role IN ('hr_user', 'hr_manager', 'admin'))
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_role ON users(role);
```

#### Documents Table

```sql
CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    filename VARCHAR(500) NOT NULL,
    original_filename VARCHAR(500) NOT NULL,
    file_type VARCHAR(50) NOT NULL,
    file_path VARCHAR(1000) NOT NULL,
    file_size BIGINT NOT NULL,
    file_hash VARCHAR(64) NOT NULL,
    extracted_text TEXT,
    doc_type VARCHAR(50),
    doc_type_confidence FLOAT,
    status VARCHAR(50) DEFAULT 'pending',
    ocr_confidence FLOAT,
    processing_error TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT valid_status CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    CONSTRAINT valid_doc_type CHECK (doc_type IN ('resume', 'report', 'contract', 'letter', 'other'))
);

CREATE INDEX idx_documents_user ON documents(user_id);
CREATE INDEX idx_documents_status ON documents(status);
CREATE INDEX idx_documents_doc_type ON documents(doc_type);
CREATE INDEX idx_documents_created ON documents(created_at DESC);
CREATE UNIQUE INDEX idx_documents_hash ON documents(file_hash);
```

#### Document Chunks Table

```sql
CREATE TABLE document_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    embedding_id VARCHAR(255),
    token_count INTEGER,
    start_position INTEGER,
    end_position INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(document_id, chunk_index)
);

CREATE INDEX idx_chunks_document ON document_chunks(document_id);
CREATE INDEX idx_chunks_embedding ON document_chunks(embedding_id);
```

#### Jobs Table

```sql
CREATE TABLE jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    required_skills TEXT[] NOT NULL,
    preferred_skills TEXT[] DEFAULT '{}',
    education_level VARCHAR(100),
    experience_min INTEGER DEFAULT 0,
    experience_max INTEGER,
    location VARCHAR(255),
    salary_min DECIMAL(12,2),
    salary_max DECIMAL(12,2),
    status VARCHAR(50) DEFAULT 'active',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT valid_job_status CHECK (status IN ('draft', 'active', 'closed', 'archived'))
);

CREATE INDEX idx_jobs_user ON jobs(user_id);
CREATE INDEX idx_jobs_status ON jobs(status);
CREATE INDEX idx_jobs_skills ON jobs USING GIN(required_skills);
```

#### Resumes Table

```sql
CREATE TABLE resumes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    candidate_name VARCHAR(255),
    email VARCHAR(255),
    phone VARCHAR(50),
    linkedin_url VARCHAR(500),
    skills TEXT[] DEFAULT '{}',
    education JSONB DEFAULT '[]',
    experience JSONB DEFAULT '[]',
    certifications TEXT[] DEFAULT '{}',
    languages TEXT[] DEFAULT '{}',
    total_experience_years FLOAT,
    parsed_data JSONB DEFAULT '{}',
    parsing_confidence FLOAT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(document_id)
);

CREATE INDEX idx_resumes_email ON resumes(email);
CREATE INDEX idx_resumes_skills ON resumes USING GIN(skills);
CREATE INDEX idx_resumes_experience ON resumes(total_experience_years);
```

#### Applications Table

```sql
CREATE TABLE applications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    resume_id UUID NOT NULL REFERENCES resumes(id) ON DELETE CASCADE,
    match_score FLOAT,
    skill_match_score FLOAT,
    experience_match_score FLOAT,
    education_match_score FLOAT,
    match_breakdown JSONB DEFAULT '{}',
    status VARCHAR(50) DEFAULT 'new',
    notes TEXT,
    reviewed_by UUID REFERENCES users(id),
    reviewed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT valid_app_status CHECK (status IN ('new', 'reviewed', 'shortlisted', 'rejected', 'interviewed', 'hired')),
    UNIQUE(job_id, resume_id)
);

CREATE INDEX idx_applications_job ON applications(job_id);
CREATE INDEX idx_applications_resume ON applications(resume_id);
CREATE INDEX idx_applications_status ON applications(status);
CREATE INDEX idx_applications_score ON applications(match_score DESC);
```

#### Email Accounts Table

```sql
CREATE TABLE email_accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    email_address VARCHAR(255) NOT NULL,
    provider VARCHAR(50) DEFAULT 'gmail',
    refresh_token TEXT,
    access_token TEXT,
    token_expiry TIMESTAMP WITH TIME ZONE,
    is_connected BOOLEAN DEFAULT FALSE,
    last_sync_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(user_id, email_address)
);

CREATE INDEX idx_email_accounts_user ON email_accounts(user_id);
```

#### Activity Logs Table

```sql
CREATE TABLE activity_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    action VARCHAR(100) NOT NULL,
    entity_type VARCHAR(50),
    entity_id UUID,
    details JSONB DEFAULT '{}',
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_activity_user ON activity_logs(user_id);
CREATE INDEX idx_activity_action ON activity_logs(action);
CREATE INDEX idx_activity_entity ON activity_logs(entity_type, entity_id);
CREATE INDEX idx_activity_created ON activity_logs(created_at DESC);
```

### 9.3 Vector Database Schema (ChromaDB)

```python
# Collection: document_embeddings
{
    "name": "document_embeddings",
    "metadata": {
        "description": "Document chunk embeddings for semantic search"
    },
    "embedding_function": "sentence-transformers/all-MiniLM-L6-v2",
    "schema": {
        "id": "string",  # UUID
        "embedding": "vector[384]",  # Embedding dimension
        "metadata": {
            "document_id": "string",
            "chunk_index": "integer",
            "doc_type": "string",
            "user_id": "string",
            "created_at": "string"
        },
        "document": "string"  # Chunk text content
    }
}

# Collection: job_embeddings
{
    "name": "job_embeddings",
    "metadata": {
        "description": "Job requirement embeddings for candidate matching"
    },
    "schema": {
        "id": "string",
        "embedding": "vector[384]",
        "metadata": {
            "job_id": "string",
            "field": "string",  # description, skills, etc.
            "user_id": "string"
        },
        "document": "string"
    }
}

# Collection: resume_embeddings
{
    "name": "resume_embeddings",
    "metadata": {
        "description": "Resume embeddings for job matching"
    },
    "schema": {
        "id": "string",
        "embedding": "vector[384]",
        "metadata": {
            "resume_id": "string",
            "document_id": "string",
            "field": "string",
            "user_id": "string"
        },
        "document": "string"
    }
}
```

---

## 10. API Specifications

### 10.1 API Overview

- **Base URL**: `/api/v1`
- **Authentication**: Bearer JWT Token
- **Content-Type**: `application/json`
- **Rate Limiting**: 100 requests/minute per user

### 10.2 Authentication Endpoints

#### POST /api/v1/auth/register

Register a new user.

**Request:**

```json
{
  "email": "user@example.com",
  "password": "SecurePass123!",
  "name": "John Doe"
}
```

**Response (201):**

```json
{
  "success": true,
  "message": "Registration successful. Please verify your email.",
  "data": {
    "user_id": "550e8400-e29b-41d4-a716-446655440000",
    "email": "user@example.com"
  }
}
```

#### POST /api/v1/auth/login

Authenticate user and get tokens.

**Request:**

```json
{
  "email": "user@example.com",
  "password": "SecurePass123!"
}
```

**Response (200):**

```json
{
  "success": true,
  "data": {
    "access_token": "eyJhbGciOiJIUzI1NiIs...",
    "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
    "token_type": "Bearer",
    "expires_in": 3600,
    "user": {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "email": "user@example.com",
      "name": "John Doe",
      "role": "hr_user"
    }
  }
}
```

#### POST /api/v1/auth/refresh

Refresh access token.

**Request:**

```json
{
  "refresh_token": "eyJhbGciOiJIUzI1NiIs..."
}
```

**Response (200):**

```json
{
  "success": true,
  "data": {
    "access_token": "eyJhbGciOiJIUzI1NiIs...",
    "expires_in": 3600
  }
}
```

#### POST /api/v1/auth/password-reset/request

Request password reset.

**Request:**

```json
{
  "email": "user@example.com"
}
```

**Response (200):**

```json
{
  "success": true,
  "message": "Password reset link sent to email."
}
```

#### POST /api/v1/auth/password-reset/confirm

Confirm password reset.

**Request:**

```json
{
  "token": "reset-token-here",
  "new_password": "NewSecurePass123!"
}
```

**Response (200):**

```json
{
  "success": true,
  "message": "Password reset successful."
}
```

### 10.3 Document Endpoints

#### POST /api/v1/documents/upload

Upload documents.

**Request:** `multipart/form-data`

- `files`: File[] (required, max 50 files)
- `doc_type`: string (optional, auto-detect if not provided)

**Response (202):**

```json
{
  "success": true,
  "message": "Documents queued for processing",
  "data": {
    "uploads": [
      {
        "document_id": "550e8400-e29b-41d4-a716-446655440001",
        "filename": "resume_john.pdf",
        "status": "processing",
        "queue_position": 1
      }
    ],
    "failed": []
  }
}
```

#### GET /api/v1/documents

List all documents.

**Query Parameters:**

- `page`: integer (default: 1)
- `limit`: integer (default: 20, max: 100)
- `status`: string (pending, processing, completed, failed)
- `doc_type`: string (resume, report, contract, letter, other)
- `sort_by`: string (created_at, filename, doc_type)
- `sort_order`: string (asc, desc)

**Response (200):**

```json
{
  "success": true,
  "data": {
    "documents": [
      {
        "id": "550e8400-e29b-41d4-a716-446655440001",
        "filename": "resume_john.pdf",
        "file_type": "pdf",
        "file_size": 125000,
        "doc_type": "resume",
        "status": "completed",
        "ocr_confidence": 0.95,
        "created_at": "2025-12-21T10:00:00Z"
      }
    ],
    "pagination": {
      "page": 1,
      "limit": 20,
      "total": 150,
      "total_pages": 8
    }
  }
}
```

#### GET /api/v1/documents/{document_id}

Get document details.

**Response (200):**

```json
{
  "success": true,
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440001",
    "filename": "resume_john.pdf",
    "original_filename": "John_Doe_Resume.pdf",
    "file_type": "pdf",
    "file_size": 125000,
    "doc_type": "resume",
    "doc_type_confidence": 0.98,
    "status": "completed",
    "ocr_confidence": 0.95,
    "extracted_text": "John Doe\nSoftware Engineer...",
    "metadata": {
      "pages": 2,
      "word_count": 450
    },
    "created_at": "2025-12-21T10:00:00Z",
    "updated_at": "2025-12-21T10:01:30Z"
  }
}
```

#### GET /api/v1/documents/{document_id}/download

Download original document.

**Response (200):** Binary file with appropriate headers

#### DELETE /api/v1/documents/{document_id}

Delete document.

**Response (200):**

```json
{
  "success": true,
  "message": "Document deleted successfully"
}
```

### 10.4 Search Endpoints

#### POST /api/v1/search

Semantic search across documents.

**Request:**

```json
{
  "query": "python developer with 5 years experience",
  "filters": {
    "doc_type": ["resume"],
    "date_from": "2025-01-01",
    "date_to": "2025-12-31"
  },
  "limit": 10,
  "offset": 0
}
```

**Response (200):**

```json
{
  "success": true,
  "data": {
    "results": [
      {
        "document_id": "550e8400-e29b-41d4-a716-446655440001",
        "filename": "resume_john.pdf",
        "doc_type": "resume",
        "relevance_score": 0.92,
        "highlights": [
          {
            "text": "...5+ years of Python development experience...",
            "chunk_index": 2
          }
        ],
        "metadata": {
          "candidate_name": "John Doe"
        }
      }
    ],
    "total": 45,
    "query_time_ms": 150
  }
}
```

#### POST /api/v1/qa

Question answering with RAG.

**Request:**

```json
{
  "question": "What are the skills of candidate John Doe?",
  "document_ids": ["550e8400-e29b-41d4-a716-446655440001"],
  "max_context_chunks": 5
}
```

**Response (200):**

```json
{
  "success": true,
  "data": {
    "answer": "Based on the resume, John Doe has the following skills:\n- Python (5+ years)\n- JavaScript/React (3 years)\n- PostgreSQL\n- Docker & Kubernetes\n- AWS services",
    "confidence": 0.89,
    "sources": [
      {
        "document_id": "550e8400-e29b-41d4-a716-446655440001",
        "filename": "resume_john.pdf",
        "chunk_index": 1,
        "relevance": 0.95
      }
    ],
    "processing_time_ms": 2500
  }
}
```

### 10.5 Job Endpoints

#### POST /api/v1/jobs

Create a new job posting.

**Request:**

```json
{
  "title": "Senior Python Developer",
  "description": "We are looking for an experienced Python developer...",
  "required_skills": ["Python", "Django", "PostgreSQL", "REST APIs"],
  "preferred_skills": ["Docker", "Kubernetes", "AWS"],
  "education_level": "Bachelor's",
  "experience_min": 5,
  "experience_max": 10,
  "location": "Lahore, Pakistan",
  "salary_min": 150000,
  "salary_max": 250000
}
```

**Response (201):**

```json
{
  "success": true,
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440010",
    "title": "Senior Python Developer",
    "status": "active",
    "created_at": "2025-12-21T10:00:00Z"
  }
}
```

#### GET /api/v1/jobs

List all jobs.

**Query Parameters:**

- `page`: integer
- `limit`: integer
- `status`: string (draft, active, closed, archived)

**Response (200):**

```json
{
    "success": true,
    "data": {
        "jobs": [
            {
                "id": "550e8400-e29b-41d4-a716-446655440010",
                "title": "Senior Python Developer",
                "status": "active",
                "application_count": 25,
                "created_at": "2025-12-21T10:00:00Z"
            }
        ],
        "pagination": {...}
    }
}
```

#### GET /api/v1/jobs/{job_id}

Get job details.

**Response (200):**

```json
{
  "success": true,
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440010",
    "title": "Senior Python Developer",
    "description": "We are looking for...",
    "required_skills": ["Python", "Django", "PostgreSQL"],
    "preferred_skills": ["Docker", "Kubernetes"],
    "education_level": "Bachelor's",
    "experience_min": 5,
    "experience_max": 10,
    "location": "Lahore, Pakistan",
    "salary_min": 150000,
    "salary_max": 250000,
    "status": "active",
    "application_count": 25,
    "created_at": "2025-12-21T10:00:00Z",
    "updated_at": "2025-12-21T10:00:00Z"
  }
}
```

#### PUT /api/v1/jobs/{job_id}

Update job posting.

**Request:**

```json
{
  "title": "Senior Python Developer (Updated)",
  "required_skills": ["Python", "Django", "FastAPI"]
}
```

**Response (200):**

```json
{
  "success": true,
  "message": "Job updated successfully"
}
```

#### DELETE /api/v1/jobs/{job_id}

Delete job posting.

**Response (200):**

```json
{
  "success": true,
  "message": "Job deleted successfully"
}
```

### 10.6 HR/Resume Endpoints

#### GET /api/v1/resumes

List all resumes.

**Query Parameters:**

- `page`, `limit`
- `skills`: string[] (filter by skills)
- `experience_min`: integer
- `experience_max`: integer

**Response (200):**

```json
{
    "success": true,
    "data": {
        "resumes": [
            {
                "id": "550e8400-e29b-41d4-a716-446655440020",
                "document_id": "550e8400-e29b-41d4-a716-446655440001",
                "candidate_name": "John Doe",
                "email": "john@example.com",
                "skills": ["Python", "Django", "PostgreSQL"],
                "total_experience_years": 5.5,
                "created_at": "2025-12-21T10:00:00Z"
            }
        ],
        "pagination": {...}
    }
}
```

#### GET /api/v1/resumes/{resume_id}

Get resume details.

**Response (200):**

```json
{
  "success": true,
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440020",
    "document_id": "550e8400-e29b-41d4-a716-446655440001",
    "candidate_name": "John Doe",
    "email": "john@example.com",
    "phone": "+92-300-1234567",
    "linkedin_url": "https://linkedin.com/in/johndoe",
    "skills": ["Python", "Django", "PostgreSQL", "Docker"],
    "education": [
      {
        "institution": "FAST NUCES",
        "degree": "BS Computer Science",
        "year": 2018,
        "gpa": 3.5
      }
    ],
    "experience": [
      {
        "company": "Tech Corp",
        "role": "Senior Developer",
        "start_date": "2020-01",
        "end_date": "present",
        "description": "Led development of..."
      }
    ],
    "certifications": ["AWS Solutions Architect"],
    "languages": ["English", "Urdu"],
    "total_experience_years": 5.5,
    "parsing_confidence": 0.92,
    "created_at": "2025-12-21T10:00:00Z"
  }
}
```

#### POST /api/v1/jobs/{job_id}/match

Match candidates to job.

**Request:**

```json
{
  "resume_ids": [], // Empty = all resumes
  "min_score": 0.5,
  "limit": 50
}
```

**Response (200):**

```json
{
  "success": true,
  "data": {
    "matches": [
      {
        "resume_id": "550e8400-e29b-41d4-a716-446655440020",
        "candidate_name": "John Doe",
        "email": "john@example.com",
        "match_score": 0.89,
        "breakdown": {
          "skill_match": 0.92,
          "experience_match": 0.85,
          "education_match": 0.9
        },
        "matched_skills": ["Python", "Django", "PostgreSQL"],
        "missing_skills": ["Kubernetes"]
      }
    ],
    "total_matched": 45,
    "processing_time_ms": 3500
  }
}
```

#### GET /api/v1/jobs/{job_id}/applications

Get applications for a job.

**Query Parameters:**

- `status`: string (new, reviewed, shortlisted, rejected, interviewed, hired)
- `sort_by`: string (match_score, created_at)

**Response (200):**

```json
{
    "success": true,
    "data": {
        "applications": [
            {
                "id": "550e8400-e29b-41d4-a716-446655440030",
                "resume_id": "550e8400-e29b-41d4-a716-446655440020",
                "candidate_name": "John Doe",
                "email": "john@example.com",
                "match_score": 0.89,
                "status": "new",
                "created_at": "2025-12-21T10:00:00Z"
            }
        ],
        "pagination": {...}
    }
}
```

#### PUT /api/v1/applications/{application_id}/status

Update application status.

**Request:**

```json
{
  "status": "shortlisted",
  "notes": "Strong candidate, schedule interview"
}
```

**Response (200):**

```json
{
  "success": true,
  "message": "Application status updated"
}
```

#### POST /api/v1/applications/export

Export applications to Excel.

**Request:**

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440010",
  "status": ["shortlisted"],
  "columns": ["candidate_name", "email", "phone", "skills", "match_score"]
}
```

**Response (200):** Excel file download

### 10.7 Email Integration Endpoints

#### POST /api/v1/email/connect

Connect Gmail account.

**Response (200):**

```json
{
  "success": true,
  "data": {
    "auth_url": "https://accounts.google.com/o/oauth2/v2/auth?..."
  }
}
```

#### GET /api/v1/email/callback

OAuth callback (internal).

#### GET /api/v1/email/status

Get email connection status.

**Response (200):**

```json
{
  "success": true,
  "data": {
    "is_connected": true,
    "email_address": "hr@company.com",
    "last_sync": "2025-12-21T09:00:00Z",
    "total_resumes_synced": 150
  }
}
```

#### POST /api/v1/email/sync

Trigger manual sync.

**Response (202):**

```json
{
  "success": true,
  "message": "Sync started",
  "data": {
    "sync_id": "550e8400-e29b-41d4-a716-446655440040"
  }
}
```

#### GET /api/v1/email/sync/{sync_id}

Get sync status.

**Response (200):**

```json
{
  "success": true,
  "data": {
    "sync_id": "550e8400-e29b-41d4-a716-446655440040",
    "status": "completed",
    "started_at": "2025-12-21T10:00:00Z",
    "completed_at": "2025-12-21T10:05:00Z",
    "new_resumes": 5,
    "duplicates_skipped": 2,
    "errors": []
  }
}
```

#### POST /api/v1/email/send

Send email to candidate.

**Request:**

```json
{
  "to": "candidate@example.com",
  "subject": "Interview Invitation - Senior Python Developer",
  "body": "Dear John,\n\nWe are pleased to invite you...",
  "attachments": []
}
```

**Response (200):**

```json
{
  "success": true,
  "message": "Email sent successfully",
  "data": {
    "message_id": "17f3a2b4c5d6e7f8"
  }
}
```

#### DELETE /api/v1/email/disconnect

Disconnect email account.

**Response (200):**

```json
{
  "success": true,
  "message": "Email account disconnected"
}
```

### 10.8 Logs Endpoints

#### GET /api/v1/logs

Get activity logs.

**Query Parameters:**

- `page`, `limit`
- `user_id`: UUID
- `action`: string
- `entity_type`: string
- `date_from`, `date_to`

**Response (200):**

```json
{
    "success": true,
    "data": {
        "logs": [
            {
                "id": "550e8400-e29b-41d4-a716-446655440050",
                "user_id": "550e8400-e29b-41d4-a716-446655440000",
                "user_name": "John Doe",
                "action": "document.upload",
                "entity_type": "document",
                "entity_id": "550e8400-e29b-41d4-a716-446655440001",
                "details": {
                    "filename": "resume.pdf"
                },
                "ip_address": "192.168.1.1",
                "created_at": "2025-12-21T10:00:00Z"
            }
        ],
        "pagination": {...}
    }
}
```

### 10.9 Error Responses

All error responses follow this format:

```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid input data",
    "details": [
      {
        "field": "email",
        "message": "Invalid email format"
      }
    ]
  }
}
```

**Error Codes:**

| Code             | HTTP Status | Description              |
| ---------------- | ----------- | ------------------------ |
| VALIDATION_ERROR | 400         | Invalid input data       |
| UNAUTHORIZED     | 401         | Authentication required  |
| FORBIDDEN        | 403         | Insufficient permissions |
| NOT_FOUND        | 404         | Resource not found       |
| CONFLICT         | 409         | Resource already exists  |
| RATE_LIMITED     | 429         | Too many requests        |
| INTERNAL_ERROR   | 500         | Server error             |

---

## 11. UI/UX Requirements

### 11.1 Design Principles

1. **Simplicity**: Clean, uncluttered interface
2. **Consistency**: Uniform patterns across all modules
3. **Feedback**: Clear visual feedback for all actions
4. **Accessibility**: WCAG 2.1 AA compliant
5. **Responsiveness**: Optimized for 1024px to 1920px

### 11.2 Page Structure

#### Navigation

```
┌────────────────────────────────────────────────────────────────────────┐
│  [Logo]    Dashboard | Documents | Search | Jobs | Candidates | Logs   │
│                                                    [User ▼] [Settings] │
└────────────────────────────────────────────────────────────────────────┘
```

#### Dashboard Page

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Dashboard                                                              │
├─────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐       │
│  │ Total Docs  │ │Active Jobs  │ │ Candidates  │ │ Shortlisted │       │
│  │    156      │ │     8       │ │    245      │ │     32      │       │
│  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘       │
│                                                                         │
│  ┌──────────────────────────────┐ ┌──────────────────────────────┐     │
│  │ Recent Documents             │ │ Recent Activity              │     │
│  │ ─────────────────────────── │ │ ───────────────────────────  │     │
│  │ resume_john.pdf    2 min ago│ │ John uploaded 3 files        │     │
│  │ contract_v2.docx   1 hr ago │ │ Sarah shortlisted 5 cand.    │     │
│  │ report_q4.pdf      3 hr ago │ │ Job "Python Dev" created     │     │
│  └──────────────────────────────┘ └──────────────────────────────┘     │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────┐      │
│  │ Quick Actions                                                 │      │
│  │ [+ Upload Documents]  [+ Create Job]  [🔍 Search]            │      │
│  └──────────────────────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────────────────────┘
```

#### Document Upload Page

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Upload Documents                                                       │
├─────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────────────────────┐      │
│  │                                                               │      │
│  │     ┌─────────────────────────────────────────────┐         │      │
│  │     │                                             │         │      │
│  │     │        📁 Drag and drop files here         │         │      │
│  │     │              or click to browse            │         │      │
│  │     │                                             │         │      │
│  │     │    Supported: PDF, DOCX, PNG, JPG          │         │      │
│  │     │    Max size: 25MB per file                 │         │      │
│  │     │                                             │         │      │
│  │     └─────────────────────────────────────────────┘         │      │
│  │                                                               │      │
│  └──────────────────────────────────────────────────────────────┘      │
│                                                                         │
│  Upload Queue:                                                          │
│  ┌──────────────────────────────────────────────────────────────┐      │
│  │ resume_john.pdf        ████████████████░░░░  80%  [Cancel]   │      │
│  │ contract.docx          ████████████████████  Done ✓          │      │
│  │ report.pdf             Waiting...                 [Cancel]   │      │
│  └──────────────────────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────────────────────┘
```

#### Search Page

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Search Documents                                                       │
├─────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────────────────────┐      │
│  │ 🔍 Find candidates with Python and 5 years experience    [Search] │  │
│  └──────────────────────────────────────────────────────────────┘      │
│                                                                         │
│  Filters: [Document Type ▼] [Date Range ▼] [Skills ▼] [Clear All]      │
│                                                                         │
│  Results (45 found) - Sorted by relevance                              │
│  ┌──────────────────────────────────────────────────────────────┐      │
│  │ 📄 resume_john_doe.pdf                           Score: 92%  │      │
│  │    Type: Resume | Uploaded: Dec 20, 2025                     │      │
│  │    "...5+ years of Python development experience at..."      │      │
│  │    [View] [Add to Shortlist]                                 │      │
│  ├──────────────────────────────────────────────────────────────┤      │
│  │ 📄 resume_sarah_ali.pdf                          Score: 87%  │      │
│  │    Type: Resume | Uploaded: Dec 19, 2025                     │      │
│  │    "...Python developer with 6 years in backend..."          │      │
│  │    [View] [Add to Shortlist]                                 │      │
│  └──────────────────────────────────────────────────────────────┘      │
│                                                                         │
│  [← Previous]  Page 1 of 5  [Next →]                                   │
└─────────────────────────────────────────────────────────────────────────┘
```

#### Q&A Interface

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Ask Questions                                                          │
├─────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────────────────────┐      │
│  │                        Chat History                           │      │
│  │  ─────────────────────────────────────────────────────────   │      │
│  │  You: What skills does John Doe have?                        │      │
│  │                                                               │      │
│  │  AI: Based on John Doe's resume, he has the following       │      │
│  │      skills:                                                 │      │
│  │      • Python (5+ years)                                     │      │
│  │      • Django & FastAPI                                      │      │
│  │      • PostgreSQL & MongoDB                                  │      │
│  │      • Docker & Kubernetes                                   │      │
│  │                                                               │      │
│  │      Sources: resume_john_doe.pdf (page 1)                   │      │
│  │  ─────────────────────────────────────────────────────────   │      │
│  │  You: Compare his experience with our requirements           │      │
│  │                                                               │      │
│  │  AI: Comparing John's profile with the Senior Python         │      │
│  │      Developer position...                                   │      │
│  │                                                               │      │
│  └──────────────────────────────────────────────────────────────┘      │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────┐      │
│  │ Ask a question about your documents...               [Send]  │      │
│  └──────────────────────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────────────────────┘
```

#### Job Management Page

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Jobs                                              [+ Create New Job]   │
├─────────────────────────────────────────────────────────────────────────┤
│  Filter: [All ▼] [Active ▼]                            Search: [____]  │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────┐      │
│  │ Senior Python Developer                                       │      │
│  │ Status: 🟢 Active | Created: Dec 15, 2025                    │      │
│  │ Applications: 25 | Shortlisted: 5                            │      │
│  │ Skills: Python, Django, PostgreSQL, Docker                   │      │
│  │ Experience: 5-10 years | Location: Lahore                    │      │
│  │ [View Applications] [Edit] [Close Job]                       │      │
│  ├──────────────────────────────────────────────────────────────┤      │
│  │ Frontend React Developer                                      │      │
│  │ Status: 🟢 Active | Created: Dec 10, 2025                    │      │
│  │ Applications: 18 | Shortlisted: 3                            │      │
│  │ [View Applications] [Edit] [Close Job]                       │      │
│  └──────────────────────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────────────────────┘
```

#### Candidate Screening Page

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Senior Python Developer - Candidates (25)                              │
├─────────────────────────────────────────────────────────────────────────┤
│  [All] [New: 15] [Shortlisted: 5] [Rejected: 5]     [Export Excel]     │
│                                                                         │
│  ┌────────────────────────────────────────────────────────────────┐    │
│  │ Rank │ Candidate    │ Match │ Skills      │ Exp  │ Actions    │    │
│  ├────────────────────────────────────────────────────────────────┤    │
│  │  1   │ John Doe     │ 92%   │ Python,     │ 5 yr │ [View]     │    │
│  │      │              │       │ Django...   │      │ [✓] [✗]    │    │
│  ├────────────────────────────────────────────────────────────────┤    │
│  │  2   │ Sarah Ali    │ 87%   │ Python,     │ 6 yr │ [View]     │    │
│  │      │              │       │ FastAPI...  │      │ [✓] [✗]    │    │
│  ├────────────────────────────────────────────────────────────────┤    │
│  │  3   │ Ahmed Khan   │ 82%   │ Python,     │ 4 yr │ [View]     │    │
│  │      │              │       │ Flask...    │      │ [✓] [✗]    │    │
│  └────────────────────────────────────────────────────────────────┘    │
│                                                                         │
│  [← Previous]  Page 1 of 3  [Next →]                                   │
└─────────────────────────────────────────────────────────────────────────┘
```

#### Candidate Detail Modal

```
┌─────────────────────────────────────────────────────────────────────────┐
│  John Doe                                    Match Score: 92%    [✕]   │
├─────────────────────────────────────────────────────────────────────────┤
│  Contact: john.doe@email.com | +92-300-1234567 | LinkedIn              │
│                                                                         │
│  ┌─────────────────────┐ ┌──────────────────────────────────────┐      │
│  │ Match Breakdown     │ │ Skills                                │      │
│  │ ───────────────     │ │ ✓ Python (Required)                   │      │
│  │ Skills:      92%    │ │ ✓ Django (Required)                   │      │
│  │ Experience:  85%    │ │ ✓ PostgreSQL (Required)               │      │
│  │ Education:   90%    │ │ ✗ Kubernetes (Preferred)              │      │
│  └─────────────────────┘ └──────────────────────────────────────┘      │
│                                                                         │
│  Experience:                                                            │
│  • Tech Corp - Senior Developer (2020 - Present)                       │
│  • StartupXYZ - Developer (2018 - 2020)                                │
│                                                                         │
│  Education:                                                             │
│  • BS Computer Science - FAST NUCES (2018)                             │
│                                                                         │
│  [View Full Resume]  [Send Email]  [Shortlist ✓]  [Reject ✗]          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 11.3 Component Library

| Component | Description                       | States                                    |
| --------- | --------------------------------- | ----------------------------------------- |
| Button    | Primary, Secondary, Danger, Ghost | Default, Hover, Active, Disabled, Loading |
| Input     | Text, Email, Password, Textarea   | Default, Focus, Error, Disabled           |
| Select    | Single, Multi-select              | Default, Open, Selected                   |
| Table     | Sortable, Filterable              | Loading, Empty, Error                     |
| Card      | Document, Job, Candidate          | Default, Hover, Selected                  |
| Modal     | Confirmation, Form, Detail        | Open, Closing                             |
| Toast     | Success, Error, Warning, Info     | Appearing, Dismissing                     |
| Progress  | Bar, Circular                     | Determinate, Indeterminate                |
| Badge     | Status, Count                     | Various colors                            |
| Tabs      | Horizontal, Vertical              | Active, Inactive                          |

### 11.4 Color Palette

```
Primary:     #2563EB (Blue)
Secondary:   #64748B (Slate)
Success:     #10B981 (Green)
Warning:     #F59E0B (Amber)
Danger:      #EF4444 (Red)
Info:        #3B82F6 (Light Blue)

Background:  #FFFFFF (White)
Surface:     #F8FAFC (Light Gray)
Border:      #E2E8F0 (Gray)
Text:        #1E293B (Dark)
Text Muted:  #64748B (Slate)
```

---

## 12. Technical Stack

### 12.1 Frontend

| Technology      | Version | Purpose          |
| --------------- | ------- | ---------------- |
| React.js        | 18.x    | UI Framework     |
| TypeScript      | 5.x     | Type Safety      |
| Vite            | 5.x     | Build Tool       |
| TailwindCSS     | 3.x     | Styling          |
| React Query     | 5.x     | Data Fetching    |
| React Router    | 6.x     | Routing          |
| Zustand         | 4.x     | State Management |
| React Hook Form | 7.x     | Form Handling    |
| Zod             | 3.x     | Validation       |
| Axios           | 1.x     | HTTP Client      |

### 12.2 Backend

| Technology | Version | Purpose         |
| ---------- | ------- | --------------- |
| Python     | 3.11+   | Runtime         |
| FastAPI    | 0.100+  | Web Framework   |
| SQLAlchemy | 2.x     | ORM             |
| Pydantic   | 2.x     | Data Validation |
| Alembic    | 1.x     | Migrations      |
| Celery     | 5.x     | Task Queue      |
| Redis      | 7.x     | Cache & Queue   |

### 12.3 AI/ML Stack

| Technology            | Version | Purpose            |
| --------------------- | ------- | ------------------ |
| LangChain             | 0.1+    | RAG Framework      |
| Sentence-Transformers | 2.x     | Embeddings         |
| ChromaDB              | 0.4+    | Vector Database    |
| Tesseract             | 5.x     | OCR                |
| PyMuPDF               | 1.x     | PDF Processing     |
| spaCy                 | 3.x     | NLP/NER            |
| OpenAI/Ollama         | -       | LLM (configurable) |

### 12.4 Infrastructure

| Technology     | Version | Purpose           |
| -------------- | ------- | ----------------- |
| PostgreSQL     | 15+     | Primary Database  |
| Redis          | 7.x     | Cache/Sessions    |
| MinIO          | Latest  | Object Storage    |
| Docker         | 24+     | Containerization  |
| Docker Compose | 2.x     | Local Development |
| Nginx          | 1.x     | Reverse Proxy     |

### 12.5 Development Tools

| Tool            | Purpose            |
| --------------- | ------------------ |
| Git             | Version Control    |
| GitHub          | Repository Hosting |
| pytest          | Testing            |
| Black           | Code Formatting    |
| Ruff            | Linting            |
| pre-commit      | Git Hooks          |
| Swagger/OpenAPI | API Documentation  |

---

## 13. Security Requirements

### 13.1 Authentication Security

| Requirement        | Implementation                                     |
| ------------------ | -------------------------------------------------- |
| Password Hashing   | bcrypt with cost factor 12                         |
| Password Policy    | Min 8 chars, 1 upper, 1 lower, 1 number, 1 special |
| JWT Tokens         | RS256 signing, 1hr access, 7d refresh              |
| Session Management | Secure, HttpOnly cookies                           |
| Rate Limiting      | 5 failed logins = 15min lockout                    |
| 2FA                | Optional TOTP support (future)                     |

### 13.2 Data Security

| Requirement           | Implementation                          |
| --------------------- | --------------------------------------- |
| Encryption at Rest    | AES-256 for sensitive data              |
| Encryption in Transit | TLS 1.3                                 |
| Database Encryption   | PostgreSQL encryption                   |
| File Encryption       | Encrypted storage for documents         |
| Key Management        | Environment variables / Secrets manager |

### 13.3 API Security

| Requirement      | Implementation            |
| ---------------- | ------------------------- |
| Authentication   | Bearer JWT tokens         |
| Authorization    | Role-based access control |
| Input Validation | Pydantic schemas          |
| SQL Injection    | Parameterized queries     |
| XSS Prevention   | Content Security Policy   |
| CSRF Protection  | SameSite cookies          |
| Rate Limiting    | 100 req/min per user      |
| CORS             | Configured origins only   |

### 13.4 Audit & Compliance

| Requirement      | Implementation                |
| ---------------- | ----------------------------- |
| Activity Logging | All user actions logged       |
| Audit Trail      | Immutable log storage         |
| Data Retention   | Configurable retention policy |
| GDPR Compliance  | Data export/deletion support  |
| Access Logs      | IP, timestamp, action logging |

---

## 14. Implementation Phases

### Phase 1: Foundation (Core Infrastructure)

**Scope:**

- Project setup and configuration
- Database schema implementation
- User authentication system
- Basic document upload and storage

**Deliverables:**

- [ ] Project repository setup with CI/CD
- [ ] Docker development environment
- [ ] PostgreSQL database with migrations
- [ ] User registration and login API
- [ ] JWT authentication middleware
- [ ] Document upload API (no processing)
- [ ] MinIO file storage integration
- [ ] Basic React frontend structure
- [ ] Login/Register UI pages

**Exit Criteria:**

- Users can register, login, and upload files
- Files stored securely in MinIO
- JWT authentication working

---

### Phase 2: Document Processing

**Scope:**

- OCR and text extraction
- Document classification
- Vector embedding generation
- Background task processing

**Deliverables:**

- [ ] Celery worker setup
- [ ] PDF text extraction (PyMuPDF)
- [ ] Image OCR (Tesseract)
- [ ] DOCX processing (python-docx)
- [ ] Document type classification
- [ ] Text chunking service
- [ ] Embedding generation (Sentence-Transformers)
- [ ] ChromaDB integration
- [ ] Document processing status API
- [ ] Document list/detail UI

**Exit Criteria:**

- Documents automatically processed after upload
- Text extracted and stored
- Embeddings generated and indexed
- Processing status visible in UI

---

### Phase 3: Search & RAG

**Scope:**

- Semantic search implementation
- RAG question answering
- Search UI

**Deliverables:**

- [ ] Semantic search API
- [ ] Search filters (type, date, metadata)
- [ ] Result ranking and scoring
- [ ] LangChain RAG pipeline
- [ ] LLM integration (OpenAI/Ollama)
- [ ] Q&A API with source citations
- [ ] Search UI with filters
- [ ] Q&A chat interface
- [ ] Result highlighting

**Exit Criteria:**

- Natural language search returning relevant results
- Q&A providing accurate answers with sources
- Search results in < 2 seconds
- Q&A responses in < 10 seconds

---

### Phase 4: HR Module - Jobs & Resumes

**Scope:**

- Resume parsing
- Job management
- Candidate matching

**Deliverables:**

- [ ] Resume parsing service (NER)
- [ ] Structured resume data extraction
- [ ] Resume API endpoints
- [ ] Job CRUD API
- [ ] Candidate matching algorithm
- [ ] Match scoring breakdown
- [ ] Application status management
- [ ] Job creation/edit UI
- [ ] Candidate list/detail UI
- [ ] Match score visualization

**Exit Criteria:**

- Resumes parsed with extracted fields
- Jobs created with requirements
- Candidates matched and ranked
- Status management working

---

### Phase 5: Email Integration

**Scope:**

- Gmail OAuth integration
- Resume sync from email
- Email sending

**Deliverables:**

- [ ] Gmail OAuth flow
- [ ] Secure token storage
- [ ] Email sync service
- [ ] Attachment extraction
- [ ] Duplicate detection
- [ ] Send email API
- [ ] Email connection UI
- [ ] Sync status UI
- [ ] Email composer UI

**Exit Criteria:**

- Gmail account connected via OAuth
- Resumes synced from email
- Emails sent to candidates

---

### Phase 6: Export & Logging

**Scope:**

- Excel export
- Activity logging
- Admin features

**Deliverables:**

- [ ] Excel export service
- [ ] Activity logging middleware
- [ ] Log query API
- [ ] Dashboard statistics API
- [ ] Export UI
- [ ] Activity log UI
- [ ] Dashboard with metrics

**Exit Criteria:**

- Data exportable to Excel
- All actions logged
- Dashboard showing key metrics

---

### Phase 7: Polish & Testing

**Scope:**

- UI refinement
- Performance optimization
- Testing
- Documentation

**Deliverables:**

- [ ] UI/UX improvements
- [ ] Performance optimization
- [ ] Unit tests (80% coverage)
- [ ] Integration tests
- [ ] API documentation (Swagger)
- [ ] User documentation
- [ ] Deployment guide

**Exit Criteria:**

- All features working smoothly
- Performance targets met
- Tests passing
- Documentation complete

---

## 15. Success Metrics

### 15.1 Technical Metrics

| Metric                   | Target  | Measurement          |
| ------------------------ | ------- | -------------------- |
| Document Processing Time | < 30s   | Average OCR time     |
| Search Response Time     | < 2s    | P95 latency          |
| RAG Response Time        | < 10s   | P95 latency          |
| System Uptime            | > 99.5% | Monthly availability |
| API Error Rate           | < 1%    | Failed requests      |
| Test Coverage            | > 80%   | Code coverage        |

### 15.2 Business Metrics

| Metric                     | Target        | Measurement         |
| -------------------------- | ------------- | ------------------- |
| Resume Screening Time      | 70% reduction | Time to shortlist   |
| Candidate Match Accuracy   | > 85%         | Relevance scoring   |
| User Adoption              | > 80%         | Active usage        |
| Document Processing Volume | 100+ daily    | Documents processed |

### 15.3 User Experience Metrics

| Metric               | Target | Measurement        |
| -------------------- | ------ | ------------------ |
| Page Load Time       | < 2s   | Initial render     |
| Task Completion Rate | > 95%  | Successful actions |
| Error Rate           | < 5%   | User-facing errors |
| User Satisfaction    | > 4/5  | Survey rating      |

---

## 16. Risks and Mitigations

### 16.1 Technical Risks

| Risk                                           | Probability | Impact | Mitigation                                              |
| ---------------------------------------------- | ----------- | ------ | ------------------------------------------------------- |
| OCR accuracy issues with low-quality documents | Medium      | Medium | Implement quality detection, manual review option       |
| LLM hallucination in Q&A                       | Medium      | High   | Use RAG with strict context, add confidence scores      |
| Performance degradation at scale               | Medium      | High   | Implement caching, optimize queries, horizontal scaling |
| Gmail API rate limits                          | Low         | Medium | Implement backoff, queue sync requests                  |
| Vector database performance                    | Low         | Medium | Index optimization, sharding strategy                   |

### 16.2 Project Risks

| Risk                   | Probability | Impact | Mitigation                                    |
| ---------------------- | ----------- | ------ | --------------------------------------------- |
| Scope creep            | Medium      | High   | Strict change management, prioritized backlog |
| Timeline delays        | Medium      | Medium | Buffer time, MVP focus                        |
| Integration complexity | Medium      | Medium | Early integration testing, modular design     |
| Resource constraints   | Low         | Medium | Cloud resources, optimized models             |

### 16.3 Security Risks

| Risk                   | Probability | Impact   | Mitigation                                 |
| ---------------------- | ----------- | -------- | ------------------------------------------ |
| Data breach            | Low         | Critical | Encryption, access controls, audit logging |
| OAuth token compromise | Low         | High     | Secure storage, token rotation             |
| SQL injection          | Low         | Critical | Parameterized queries, input validation    |
| Unauthorized access    | Low         | High     | RBAC, session management                   |

---

## 17. Glossary

| Term                 | Definition                                                                       |
| -------------------- | -------------------------------------------------------------------------------- |
| **RAG**              | Retrieval-Augmented Generation - AI technique combining retrieval and generation |
| **OCR**              | Optical Character Recognition - Converting images to text                        |
| **NER**              | Named Entity Recognition - Extracting entities from text                         |
| **Vector Embedding** | Numerical representation of text for similarity search                           |
| **Semantic Search**  | Search based on meaning rather than keywords                                     |
| **LLM**              | Large Language Model - AI model for text generation                              |
| **JWT**              | JSON Web Token - Authentication token format                                     |
| **OAuth**            | Open Authorization - Authentication protocol                                     |
| **CRUD**             | Create, Read, Update, Delete - Basic operations                                  |
| **API**              | Application Programming Interface                                                |
| **REST**             | Representational State Transfer - API architecture                               |
| **RBAC**             | Role-Based Access Control                                                        |
| **CI/CD**            | Continuous Integration/Continuous Deployment                                     |

---

## Appendix A: File Structure

```
hr-screening-rag/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── deps.py
│   │   │   ├── v1/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── auth.py
│   │   │   │   ├── documents.py
│   │   │   │   ├── search.py
│   │   │   │   ├── jobs.py
│   │   │   │   ├── resumes.py
│   │   │   │   ├── email.py
│   │   │   │   └── logs.py
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── user.py
│   │   │   ├── document.py
│   │   │   ├── job.py
│   │   │   ├── resume.py
│   │   │   └── log.py
│   │   ├── schemas/
│   │   │   ├── __init__.py
│   │   │   ├── user.py
│   │   │   ├── document.py
│   │   │   ├── job.py
│   │   │   └── resume.py
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── auth.py
│   │   │   ├── document.py
│   │   │   ├── ocr.py
│   │   │   ├── embedding.py
│   │   │   ├── search.py
│   │   │   ├── rag.py
│   │   │   ├── resume_parser.py
│   │   │   ├── matching.py
│   │   │   └── email.py
│   │   ├── workers/
│   │   │   ├── __init__.py
│   │   │   ├── celery_app.py
│   │   │   └── tasks.py
│   │   └── utils/
│   │       ├── __init__.py
│   │       ├── security.py
│   │       └── helpers.py
│   ├── alembic/
│   │   ├── versions/
│   │   └── env.py
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── conftest.py
│   │   ├── test_auth.py
│   │   ├── test_documents.py
│   │   └── test_search.py
│   ├── requirements.txt
│   ├── Dockerfile
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── api/
│   │   │   ├── client.ts
│   │   │   ├── auth.ts
│   │   │   ├── documents.ts
│   │   │   ├── jobs.ts
│   │   │   └── search.ts
│   │   ├── components/
│   │   │   ├── ui/
│   │   │   ├── layout/
│   │   │   ├── documents/
│   │   │   ├── jobs/
│   │   │   └── candidates/
│   │   ├── pages/
│   │   │   ├── Dashboard.tsx
│   │   │   ├── Login.tsx
│   │   │   ├── Documents.tsx
│   │   │   ├── Search.tsx
│   │   │   ├── Jobs.tsx
│   │   │   └── Candidates.tsx
│   │   ├── hooks/
│   │   ├── store/
│   │   ├── types/
│   │   └── utils/
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   └── Dockerfile
├── docker-compose.yml
├── docker-compose.prod.yml
├── .env.example
├── .gitignore
├── README.md
└── PRD.md
```

---

## Appendix B: Environment Variables

```bash
# Application
APP_NAME=hr-screening-rag
APP_ENV=development
DEBUG=true
SECRET_KEY=your-secret-key-here

# Database
DATABASE_URL=postgresql://user:password@localhost:5432/hr_rag
DATABASE_POOL_SIZE=10

# Redis
REDIS_URL=redis://localhost:6379/0

# MinIO
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=documents

# ChromaDB
CHROMA_HOST=localhost
CHROMA_PORT=8000

# JWT
JWT_SECRET_KEY=your-jwt-secret
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
REFRESH_TOKEN_EXPIRE_DAYS=7

# Gmail OAuth
GOOGLE_CLIENT_ID=your-client-id
GOOGLE_CLIENT_SECRET=your-client-secret
GOOGLE_REDIRECT_URI=http://localhost:8000/api/v1/email/callback

# LLM
LLM_PROVIDER=openai  # or ollama
OPENAI_API_KEY=your-openai-key
OLLAMA_HOST=http://localhost:11434

# Embeddings
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2

# Frontend
VITE_API_URL=http://localhost:8000/api/v1
```

---

**Document Version History:**

| Version | Date         | Author | Changes     |
| ------- | ------------ | ------ | ----------- |
| 1.0     | Dec 21, 2025 | Team   | Initial PRD |

---

_This PRD is a living document and will be updated as the project evolves._
