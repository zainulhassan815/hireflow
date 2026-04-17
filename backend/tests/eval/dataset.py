"""Fixture documents and evaluation queries.

Docs are plaintext; the harness seeds them directly into Postgres +
ChromaDB (bypassing the upload/extraction pipeline so the eval
measures search, not extraction). Each doc has realistic metadata
so the SQL filter path has something to match when a query provides
``skills=`` etc.

Queries are grouped into buckets; per-bucket aggregates are printed
alongside the overall numbers so we can see which query shapes we're
weak on.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.models import DocumentType


@dataclass(frozen=True)
class FixtureDoc:
    """A seed document for the eval harness."""

    slug: str
    filename: str
    document_type: DocumentType
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvalCase:
    """One (query, expected answer) row."""

    query: str
    expected_docs: set[str]
    must_not_contain: set[str] = field(default_factory=set)
    bucket: str = "misc"
    notes: str = ""
    filters: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Fixture documents
# ---------------------------------------------------------------------------

_PYTHON_SENIOR = """Jane Doe — Senior Backend Engineer

Summary
  10+ years building high-availability Python services on AWS.
  Strong background in Kubernetes, PostgreSQL, and distributed
  systems. Comfortable leading small teams and mentoring juniors.

Skills
  Python, Django, FastAPI, Celery, PostgreSQL, Redis, Docker,
  Kubernetes, AWS (EC2, RDS, S3, Lambda), Terraform, GitHub Actions,
  gRPC, Kafka.

Experience
  Senior Backend Engineer — Stripe (2019–present)
    Led migration of the billing service to event-driven architecture.
    Reduced p99 latency from 600ms to 90ms.

  Backend Engineer — Shopify (2015–2019)
    Owned the orders pipeline. Built the async job framework
    on top of Redis/RQ.

Education
  BSc Computer Science, University of Toronto, 2014.
"""

_JAVASCRIPT_JUNIOR = """Alex Smith — Junior Frontend Developer

Summary
  Bootcamp graduate with two internships and a year of full-time
  experience. Enthusiastic about React, TypeScript, and modern web
  tooling.

Skills
  JavaScript, TypeScript, React, Next.js, Tailwind CSS, Jest,
  Playwright, Node.js (basic), Figma.

Experience
  Frontend Developer — Acme Corp (2023–present)
    Built dashboard UIs in React + Tailwind. Migrated legacy jQuery
    screens to modern SPA.

  Frontend Intern — Stripe (Summer 2022, Summer 2023)
    Worked on the billing UI and developer docs.

Education
  General Assembly Web Development Bootcamp, 2022.
"""

_DATA_SCIENTIST = """Priya Patel — Data Scientist

Summary
  Machine-learning practitioner with 6 years in ad-tech and healthtech.
  Focus on recommendation systems, NLP, and production ML pipelines.

Skills
  Python, PyTorch, TensorFlow, Scikit-learn, Pandas, NumPy,
  SQL, Airflow, Kubeflow, Spark, AWS SageMaker, MLflow, Jupyter,
  statistics, A/B testing.

Experience
  Senior Data Scientist — Flatiron Health (2021–present)
    Led the oncology recommendation system. Deployed an NLP model
    for parsing clinical notes.

  Data Scientist — Criteo (2018–2021)
    Built real-time bidding models and feature stores.

Education
  MSc Statistics, Stanford University, 2018.
  BSc Mathematics, IIT Bombay, 2016.
"""

_DEVOPS_ENGINEER = """Marcus Chen — DevOps / SRE

Summary
  Seven years building platform infrastructure. Deep expertise in
  Kubernetes, observability, and incident response.

Skills
  Kubernetes, Helm, ArgoCD, Terraform, Prometheus, Grafana,
  Datadog, PagerDuty, AWS, GCP, Python, Go, Bash, Ansible,
  Jenkins, GitHub Actions.

Experience
  Staff SRE — Cloudflare (2022–present)
    On-call rotation for the edge network. Owned the incident
    retrospective process.

  DevOps Engineer — HashiCorp (2017–2022)
    Maintained the internal Terraform Enterprise deployment.

Education
  BEng Computer Engineering, McMaster University, 2017.
"""

_VENDOR_CONTRACT = """Vendor Service Agreement — Q3 2025

This Master Services Agreement ("Agreement") is entered into on
July 1, 2025, by and between Acme Holdings Inc. ("Client") and
Brightforge Consulting LLC ("Vendor").

1. Scope of Services
   Vendor shall provide managed DevOps consulting services to
   Client for a term of twelve (12) months commencing on the
   effective date.

2. Fees and Payment
   Client shall pay Vendor a monthly retainer of $45,000 USD,
   invoiced on the first business day of each month. Late payments
   accrue interest at 1.5% per month.

3. Confidentiality
   Each party agrees to maintain the confidentiality of proprietary
   information disclosed by the other party. Obligations survive
   termination for a period of three (3) years.

4. Termination
   Either party may terminate this Agreement for convenience with
   sixty (60) days written notice. Termination for cause requires
   a material breach remaining uncured after thirty (30) days notice.
"""

_Q3_SALES_REPORT = """Q3 2025 Sales Performance Report

Executive Summary
  Q3 revenue landed at $12.4M, a 14% year-over-year increase and
  3% above plan. Growth was driven by expansion in the enterprise
  segment and stronger North American results. EMEA underperformed
  plan by 8%, primarily due to slippage in two large deals.

Regional Breakdown
  North America: $7.8M (+22% YoY)
  EMEA:          $2.9M (-4% YoY, -8% vs plan)
  APAC:          $1.7M (+11% YoY)

Pipeline Health
  Open opportunities: $34M weighted.
  Average deal size: $180K (up from $145K in Q2).
  Win rate: 31%, steady vs Q2.

Key Wins
  - Closed $2.1M three-year deal with Northwind Health.
  - Renewed $1.4M with Globex Financial (2-year extension).

Risks for Q4
  - Three EMEA deals ($3.2M combined) pushed from Q3 to Q4.
  - Seasonal slowdown historically trims Q4 close rates by ~10%.
"""

_COVER_LETTER = """Dear Hiring Manager,

I am writing to express my strong interest in the Senior Backend
Engineer position at Hireflow. With ten years of experience building
high-throughput Python services at Stripe and Shopify, I believe I
would be an excellent fit for your platform team.

In my current role, I have led the migration of several legacy
services to event-driven architectures on AWS, reducing latency and
improving reliability. I am particularly drawn to Hireflow's focus
on production-grade hiring infrastructure and your commitment to
careful engineering.

I would welcome the opportunity to discuss how my background aligns
with your team's priorities. Thank you for your consideration.

Sincerely,
Jane Doe
"""


FIXTURE_DOCS: list[FixtureDoc] = [
    FixtureDoc(
        slug="resume_python_senior",
        filename="jane_doe_resume.pdf",
        document_type=DocumentType.RESUME,
        text=_PYTHON_SENIOR,
        metadata={
            "name": "Jane Doe",
            "emails": ["jane@example.com"],
            "skills": [
                "python",
                "django",
                "fastapi",
                "postgresql",
                "redis",
                "docker",
                "kubernetes",
                "aws",
                "terraform",
            ],
            "experience_years": 10,
            "education": ["BSc Computer Science"],
        },
    ),
    FixtureDoc(
        slug="resume_javascript_junior",
        filename="alex_smith_resume.pdf",
        document_type=DocumentType.RESUME,
        text=_JAVASCRIPT_JUNIOR,
        metadata={
            "name": "Alex Smith",
            "emails": ["alex@example.com"],
            "skills": [
                "javascript",
                "typescript",
                "react",
                "nextjs",
                "tailwind",
                "jest",
                "playwright",
            ],
            "experience_years": 1,
            "education": ["Bootcamp"],
        },
    ),
    FixtureDoc(
        slug="resume_data_scientist",
        filename="priya_patel_resume.pdf",
        document_type=DocumentType.RESUME,
        text=_DATA_SCIENTIST,
        metadata={
            "name": "Priya Patel",
            "emails": ["priya@example.com"],
            "skills": [
                "python",
                "pytorch",
                "tensorflow",
                "scikit-learn",
                "sql",
                "airflow",
                "spark",
                "aws",
            ],
            "experience_years": 6,
            "education": ["MSc Statistics", "BSc Mathematics"],
        },
    ),
    FixtureDoc(
        slug="resume_devops",
        filename="marcus_chen_resume.pdf",
        document_type=DocumentType.RESUME,
        text=_DEVOPS_ENGINEER,
        metadata={
            "name": "Marcus Chen",
            "emails": ["marcus@example.com"],
            "skills": [
                "kubernetes",
                "helm",
                "terraform",
                "prometheus",
                "grafana",
                "aws",
                "gcp",
                "python",
                "go",
            ],
            "experience_years": 7,
            "education": ["BEng Computer Engineering"],
        },
    ),
    FixtureDoc(
        slug="contract_vendor_q3",
        filename="brightforge_msa.pdf",
        document_type=DocumentType.CONTRACT,
        text=_VENDOR_CONTRACT,
        metadata={
            "document_category": "vendor_agreement",
            "counterparty": "Brightforge",
        },
    ),
    FixtureDoc(
        slug="report_sales_q3",
        filename="q3_2025_sales.pdf",
        document_type=DocumentType.REPORT,
        text=_Q3_SALES_REPORT,
        metadata={"report_type": "sales", "period": "Q3 2025"},
    ),
    FixtureDoc(
        slug="letter_cover_jane",
        filename="jane_doe_cover_letter.pdf",
        document_type=DocumentType.LETTER,
        text=_COVER_LETTER,
        metadata={"letter_type": "cover_letter", "applicant": "Jane Doe"},
    ),
]


# ---------------------------------------------------------------------------
# Evaluation queries
# ---------------------------------------------------------------------------

EVAL_QUERIES: list[EvalCase] = [
    # ---- role / skill ----
    EvalCase(
        query="Python backend engineer with AWS experience",
        expected_docs={"resume_python_senior", "resume_data_scientist"},
        must_not_contain={"contract_vendor_q3", "report_sales_q3"},
        bucket="role_skill",
        notes="Python + cloud; DS is also plausible",
    ),
    EvalCase(
        query="React developer",
        expected_docs={"resume_javascript_junior"},
        must_not_contain={"contract_vendor_q3", "report_sales_q3"},
        bucket="role_skill",
    ),
    EvalCase(
        query="Kubernetes SRE",
        expected_docs={"resume_devops"},
        must_not_contain={"contract_vendor_q3", "report_sales_q3"},
        bucket="role_skill",
    ),
    EvalCase(
        query="machine learning engineer with PyTorch",
        expected_docs={"resume_data_scientist"},
        must_not_contain={"contract_vendor_q3"},
        bucket="role_skill",
    ),
    EvalCase(
        query="senior engineer 10 years experience",
        expected_docs={"resume_python_senior"},
        bucket="role_skill",
        notes="seniority implied",
    ),
    # ---- document type ----
    EvalCase(
        query="vendor services agreement",
        expected_docs={"contract_vendor_q3"},
        must_not_contain={"resume_python_senior", "resume_javascript_junior"},
        bucket="doc_type",
    ),
    EvalCase(
        query="quarterly sales report",
        expected_docs={"report_sales_q3"},
        must_not_contain={"resume_python_senior", "resume_javascript_junior"},
        bucket="doc_type",
    ),
    EvalCase(
        query="cover letter for engineering role",
        expected_docs={"letter_cover_jane"},
        bucket="doc_type",
    ),
    # ---- negative (should return nothing above threshold) ----
    EvalCase(
        query="quantum chromodynamics tensor networks",
        expected_docs=set(),
        must_not_contain={d.slug for d in FIXTURE_DOCS},
        bucket="negative",
        notes="irrelevant topic; threshold should drop everything",
    ),
    EvalCase(
        query="recipe for sourdough bread",
        expected_docs=set(),
        must_not_contain={d.slug for d in FIXTURE_DOCS},
        bucket="negative",
    ),
    # ---- structured filter (exercises SQL path) ----
    EvalCase(
        query="senior engineer",
        filters={"skills": ["kubernetes"]},
        expected_docs={"resume_devops", "resume_python_senior"},
        bucket="filtered",
        notes="semantic + skill filter",
    ),
    EvalCase(
        query="anyone",
        filters={"document_type": "report"},
        expected_docs={"report_sales_q3"},
        must_not_contain={
            "resume_python_senior",
            "resume_javascript_junior",
            "resume_data_scientist",
            "resume_devops",
            "contract_vendor_q3",
            "letter_cover_jane",
        },
        bucket="filtered",
        notes="type filter dominates",
    ),
    EvalCase(
        query="python",
        filters={"min_experience_years": 5},
        expected_docs={
            "resume_python_senior",
            "resume_data_scientist",
            "resume_devops",
        },
        must_not_contain={"resume_javascript_junior"},
        bucket="filtered",
        notes="seniority filter excludes junior",
    ),
    # ---- edge queries ----
    EvalCase(
        query="python",
        expected_docs={
            "resume_python_senior",
            "resume_data_scientist",
            "resume_devops",
        },
        bucket="edge",
        notes="single word",
    ),
    EvalCase(
        query="Q3 EMEA revenue and deal slippage",
        expected_docs={"report_sales_q3"},
        bucket="edge",
        notes="specific phrase that should match only the report",
    ),
    EvalCase(
        query="terraform",
        expected_docs={"resume_python_senior", "resume_devops"},
        bucket="edge",
        notes="single skill",
    ),
]
