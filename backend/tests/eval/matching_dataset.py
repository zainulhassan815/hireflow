"""Fixture corpus for the candidate-matching eval (F45.a).

Twelve candidate résumés and four jobs, each job paired with a
human-labeled ideal ranking. The harness runs ``MatchingService`` and
measures how close its ranking comes to these labels.

Résumés are plaintext; the harness seeds them straight into Postgres +
ChromaDB so the vector signal is live. Skills / experience live on the
seeded ``Candidate`` row — that is what the skill and experience signals
read. ``cand_coldstart`` deliberately has empty ``skills`` (extraction
"failed"): the model scores it 0 on the skill component even though the
résumé text is a strong backend fit — that gap is the F45.f datapoint.

NOTE: this module **must not** import anything from ``app.*`` at module
level — importing ``app.core.config`` before pytest swaps in the test DB
URL once wiped a dev database (see the same warning in ``dataset.py``).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CandidateFixture:
    """One seed candidate: a résumé document plus its parsed metadata."""

    slug: str
    filename: str
    name: str
    experience_years: int
    skills: tuple[str, ...]
    resume_text: str


@dataclass(frozen=True)
class JobFixture:
    """One seed job opening."""

    slug: str
    title: str
    description: str
    required_skills: tuple[str, ...]
    preferred_skills: tuple[str, ...]
    experience_min: int
    experience_max: int | None


@dataclass(frozen=True)
class MatchCase:
    """A job paired with its human-labeled ideal candidate ranking.

    ``expected_ranking`` lists every candidate slug best→worst.
    ``must_not_top`` are candidates it would be a clear regression to
    rank #1 for this job — the harness hard-fails on a violation.
    """

    job_slug: str
    expected_ranking: tuple[str, ...]
    must_not_top: frozenset[str]
    notes: str = ""


# ---------------------------------------------------------------------------
# Candidate résumés
# ---------------------------------------------------------------------------

_BACKEND_SENIOR = """Daniel Okafor — Senior Backend Engineer

SUMMARY
  Nine years building high-throughput Python services and APIs.
  Owns billing and payments platforms end to end.

SKILLS
  Python, FastAPI, Django, PostgreSQL, Redis, Docker, Kubernetes, AWS.

EXPERIENCE
  Senior Backend Engineer — Paywell (2018-present)
    Designed an event-driven billing service on FastAPI and Postgres.
  Backend Engineer — Shopline (2015-2018)
    Built the async order pipeline on Redis.

EDUCATION
  BSc Computer Science, 2015.
"""

_BACKEND_MID = """Sara Lindqvist — Backend Engineer

SUMMARY
  Four years writing Python web services. Comfortable owning a
  service from API design through deployment.

SKILLS
  Python, FastAPI, PostgreSQL, Docker.

EXPERIENCE
  Backend Engineer — Tessera (2021-present)
    Built and maintained REST APIs on FastAPI and PostgreSQL.

EDUCATION
  BSc Software Engineering, 2021.
"""

_BACKEND_JUNIOR = """Tom Becker — Junior Backend Developer

SUMMARY
  One year of backend work after a computer-science degree.
  Eager to grow into API and database design.

SKILLS
  Python, Flask, SQL.

EXPERIENCE
  Junior Developer — Brightloop (2024-present)
    Maintained internal Flask tools and SQL reports.

EDUCATION
  BSc Computer Science, 2024.
"""

_FRONTEND_SENIOR = """Mei Tanaka — Senior Frontend Engineer

SUMMARY
  Eight years building modern web interfaces. Leads a small UI
  platform team.

SKILLS
  React, TypeScript, JavaScript, Next.js, Tailwind, Jest.

EXPERIENCE
  Senior Frontend Engineer — Vantage (2019-present)
    Owns the design-system and component library in React + TypeScript.
  Frontend Developer — Glimpse (2016-2019)
    Built dashboard UIs.

EDUCATION
  BSc Interaction Design, 2016.
"""

_FRONTEND_MID = """Lucas Moreau — Frontend Developer

SUMMARY
  Three years building single-page applications with React.

SKILLS
  React, TypeScript, JavaScript, CSS.

EXPERIENCE
  Frontend Developer — Northwind (2022-present)
    Built customer-facing React screens and migrated legacy pages.

EDUCATION
  BSc Computer Science, 2022.
"""

_FRONTEND_JUNIOR = """Aisha Bello — Junior Frontend Developer

SUMMARY
  One year of frontend work after a web-development bootcamp.

SKILLS
  JavaScript, React, HTML.

EXPERIENCE
  Junior Frontend Developer — Marketly (2024-present)
    Built marketing pages and small React widgets.

EDUCATION
  Web Development Bootcamp, 2024.
"""

_DEVOPS_SENIOR = """Viktor Petrov — Senior DevOps / SRE

SUMMARY
  Eight years running platform infrastructure and on-call rotations.

SKILLS
  Kubernetes, Terraform, AWS, Prometheus, Docker, Python, Ansible.

EXPERIENCE
  Staff SRE — Edgecast (2020-present)
    Owns the Kubernetes platform and incident-response process.
  DevOps Engineer — Cloudpoint (2016-2020)
    Maintained Terraform-managed AWS infrastructure.

EDUCATION
  BEng Computer Engineering, 2016.
"""

_DEVOPS_MID = """Grace Mwangi — DevOps Engineer

SUMMARY
  Four years keeping deployment pipelines and clusters healthy.

SKILLS
  Kubernetes, Docker, AWS, Bash.

EXPERIENCE
  DevOps Engineer — Relay (2021-present)
    Ran the Kubernetes clusters and CI/CD pipelines on AWS.

EDUCATION
  BSc Information Systems, 2021.
"""

_DATA_SENIOR = """Ravi Sharma — Senior Data Scientist

SUMMARY
  Seven years building machine-learning models and data pipelines.

SKILLS
  Python, PyTorch, TensorFlow, SQL, Pandas, statistics, Spark, AWS.

EXPERIENCE
  Senior Data Scientist — Healthgrid (2020-present)
    Led recommendation models and a PySpark feature pipeline.
  Data Scientist — Admetric (2017-2020)
    Built bidding models and ran A/B experiments.

EDUCATION
  MSc Statistics, 2017.
"""

_DATA_MID = """Elena Costa — Data Scientist

SUMMARY
  Three years building predictive models and analytics pipelines.

SKILLS
  Python, SQL, Pandas, scikit-learn.

EXPERIENCE
  Data Scientist — Loomis (2022-present)
    Built churn models and SQL analytics on top of Pandas pipelines.

EDUCATION
  BSc Mathematics, 2022.
"""

_GENERALIST = """Noah Klein — Full-Stack Engineer

SUMMARY
  Five years shipping full-stack products — backend services, web
  UIs, and the infrastructure underneath them.

SKILLS
  Python, JavaScript, React, PostgreSQL, Docker, AWS.

EXPERIENCE
  Full-Stack Engineer — Junction (2020-present)
    Built React frontends and Python APIs; ran the AWS deployment.

EDUCATION
  BSc Computer Science, 2020.
"""

# Strong senior-backend résumé, but the seeded Candidate row has empty
# skills — simulates a résumé whose skill extraction failed (F45.f).
_COLDSTART = """Priya Nair — Senior Backend Engineer

SUMMARY
  Eight years building Python backend services, REST APIs, and
  PostgreSQL-backed data platforms at scale.

EXPERIENCE
  Senior Backend Engineer — Stratos (2019-present)
    Led the migration of a monolith to FastAPI microservices.
    Tuned PostgreSQL and Redis caching to cut p99 latency.
  Backend Engineer — Corebridge (2016-2019)
    Built high-throughput payment APIs on Python and Docker.

EDUCATION
  BSc Computer Science, 2016.
"""


MATCH_CANDIDATES: list[CandidateFixture] = [
    CandidateFixture(
        slug="cand_backend_senior",
        filename="daniel_okafor_resume.pdf",
        name="Daniel Okafor",
        experience_years=9,
        skills=(
            "python",
            "fastapi",
            "django",
            "postgresql",
            "redis",
            "docker",
            "kubernetes",
            "aws",
        ),
        resume_text=_BACKEND_SENIOR,
    ),
    CandidateFixture(
        slug="cand_backend_mid",
        filename="sara_lindqvist_resume.pdf",
        name="Sara Lindqvist",
        experience_years=4,
        skills=("python", "fastapi", "postgresql", "docker"),
        resume_text=_BACKEND_MID,
    ),
    CandidateFixture(
        slug="cand_backend_junior",
        filename="tom_becker_resume.pdf",
        name="Tom Becker",
        experience_years=1,
        skills=("python", "flask", "sql"),
        resume_text=_BACKEND_JUNIOR,
    ),
    CandidateFixture(
        slug="cand_frontend_senior",
        filename="mei_tanaka_resume.pdf",
        name="Mei Tanaka",
        experience_years=8,
        skills=("react", "typescript", "javascript", "nextjs", "tailwind", "jest"),
        resume_text=_FRONTEND_SENIOR,
    ),
    CandidateFixture(
        slug="cand_frontend_mid",
        filename="lucas_moreau_resume.pdf",
        name="Lucas Moreau",
        experience_years=3,
        skills=("react", "typescript", "javascript", "css"),
        resume_text=_FRONTEND_MID,
    ),
    CandidateFixture(
        slug="cand_frontend_junior",
        filename="aisha_bello_resume.pdf",
        name="Aisha Bello",
        experience_years=1,
        skills=("javascript", "react", "html"),
        resume_text=_FRONTEND_JUNIOR,
    ),
    CandidateFixture(
        slug="cand_devops_senior",
        filename="viktor_petrov_resume.pdf",
        name="Viktor Petrov",
        experience_years=8,
        skills=(
            "kubernetes",
            "terraform",
            "aws",
            "prometheus",
            "docker",
            "python",
            "ansible",
        ),
        resume_text=_DEVOPS_SENIOR,
    ),
    CandidateFixture(
        slug="cand_devops_mid",
        filename="grace_mwangi_resume.pdf",
        name="Grace Mwangi",
        experience_years=4,
        skills=("kubernetes", "docker", "aws", "bash"),
        resume_text=_DEVOPS_MID,
    ),
    CandidateFixture(
        slug="cand_data_senior",
        filename="ravi_sharma_resume.pdf",
        name="Ravi Sharma",
        experience_years=7,
        skills=(
            "python",
            "pytorch",
            "tensorflow",
            "sql",
            "pandas",
            "statistics",
            "spark",
            "aws",
        ),
        resume_text=_DATA_SENIOR,
    ),
    CandidateFixture(
        slug="cand_data_mid",
        filename="elena_costa_resume.pdf",
        name="Elena Costa",
        experience_years=3,
        skills=("python", "sql", "pandas", "scikit-learn"),
        resume_text=_DATA_MID,
    ),
    CandidateFixture(
        slug="cand_generalist",
        filename="noah_klein_resume.pdf",
        name="Noah Klein",
        experience_years=5,
        skills=("python", "javascript", "react", "postgresql", "docker", "aws"),
        resume_text=_GENERALIST,
    ),
    CandidateFixture(
        slug="cand_coldstart",
        filename="priya_nair_resume.pdf",
        name="Priya Nair",
        experience_years=8,
        skills=(),  # extraction failed — F45.f cold-start case
        resume_text=_COLDSTART,
    ),
]


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

MATCH_JOBS: list[JobFixture] = [
    JobFixture(
        slug="job_senior_backend",
        title="Senior Backend Engineer",
        description=(
            "Build and own high-throughput Python backend services and "
            "REST APIs. Design PostgreSQL data models and ship to a "
            "containerised cloud environment. Mentor mid-level engineers."
        ),
        required_skills=("python", "fastapi", "postgresql"),
        preferred_skills=("kubernetes", "aws", "redis"),
        experience_min=6,
        experience_max=12,
    ),
    JobFixture(
        slug="job_frontend",
        title="Frontend Engineer",
        description=(
            "Build modern, accessible web interfaces with React and "
            "TypeScript. Own components from design through test and "
            "ship customer-facing single-page applications."
        ),
        required_skills=("react", "typescript", "javascript"),
        preferred_skills=("nextjs", "tailwind", "jest"),
        experience_min=2,
        experience_max=8,
    ),
    JobFixture(
        slug="job_devops",
        title="DevOps / SRE Engineer",
        description=(
            "Run platform infrastructure on Kubernetes and AWS. Manage "
            "Terraform-defined environments, build observability, and "
            "own the incident-response process."
        ),
        required_skills=("kubernetes", "terraform", "aws"),
        preferred_skills=("prometheus", "docker", "python"),
        experience_min=4,
        experience_max=12,
    ),
    JobFixture(
        slug="job_data_scientist",
        title="Data Scientist",
        description=(
            "Build machine-learning models and data pipelines. Run "
            "experiments, analyse results with Python and SQL, and move "
            "models into production."
        ),
        required_skills=("python", "sql", "pandas"),
        preferred_skills=("pytorch", "statistics", "spark"),
        experience_min=3,
        experience_max=10,
    ),
]


# ---------------------------------------------------------------------------
# Labeled match cases — human-judged ideal ranking per job
# ---------------------------------------------------------------------------

MATCH_CASES: list[MatchCase] = [
    MatchCase(
        job_slug="job_senior_backend",
        expected_ranking=(
            "cand_backend_senior",  # perfect skills, senior, on-domain
            "cand_generalist",  # python+postgres+cloud, slightly junior
            "cand_backend_mid",  # right skills, under the seniority bar
            "cand_devops_senior",  # python + cloud, infra-leaning senior
            "cand_data_senior",  # python, senior, but data not backend
            "cand_coldstart",  # true fit is high; capped mid (F45.f)
            "cand_data_mid",  # python only, junior
            "cand_backend_junior",  # on-domain intent, 1y, thin skills
            "cand_devops_mid",  # infra, no python
            "cand_frontend_senior",  # wrong domain
            "cand_frontend_mid",
            "cand_frontend_junior",
        ),
        must_not_top=frozenset(
            {"cand_backend_junior", "cand_frontend_mid", "cand_frontend_junior"}
        ),
        notes=(
            "Domain + seniority + skill depth. cand_coldstart is genuinely "
            "a top-2 fit but is labeled mid-tier so its zero skill score "
            "doesn't dominate Spearman — the model/expected gap here is the "
            "intended F45.f measurement."
        ),
    ),
    MatchCase(
        job_slug="job_frontend",
        expected_ranking=(
            "cand_frontend_senior",  # perfect, senior
            "cand_frontend_mid",  # react/ts/js, mid
            "cand_frontend_junior",  # on-domain, just under exp floor
            "cand_generalist",  # react+js but no typescript
            "cand_backend_senior",  # strong engineer, wrong domain
            "cand_devops_senior",
            "cand_data_senior",
            "cand_backend_mid",
            "cand_data_mid",
            "cand_devops_mid",
            "cand_backend_junior",
            "cand_coldstart",  # backend résumé, no skills — genuine poor fit
        ),
        must_not_top=frozenset(
            {"cand_backend_junior", "cand_devops_mid", "cand_data_mid"}
        ),
        notes="Frontend skills dominate; coldstart honestly ranks last here.",
    ),
    MatchCase(
        job_slug="job_devops",
        expected_ranking=(
            "cand_devops_senior",  # perfect
            "cand_devops_mid",  # k8s+docker+aws, missing terraform
            "cand_generalist",  # aws+docker+python
            "cand_backend_senior",  # carries k8s/aws/docker + python
            "cand_data_senior",  # python + aws, senior
            "cand_backend_mid",  # docker + python
            "cand_data_mid",  # python only
            "cand_coldstart",  # backend résumé, no skills
            "cand_backend_junior",
            "cand_frontend_senior",
            "cand_frontend_mid",
            "cand_frontend_junior",
        ),
        must_not_top=frozenset(
            {"cand_backend_junior", "cand_frontend_mid", "cand_frontend_junior"}
        ),
        notes="Infra skills + cloud experience drive the order.",
    ),
    MatchCase(
        job_slug="job_data_scientist",
        expected_ranking=(
            "cand_data_senior",  # all required + all preferred
            "cand_data_mid",  # python+sql+pandas, mid
            "cand_generalist",  # python only of the required set
            "cand_backend_senior",  # python, senior, no data stack
            "cand_backend_mid",  # python
            "cand_devops_senior",  # python, senior
            "cand_backend_junior",  # python+sql, junior
            "cand_coldstart",  # backend résumé, no skills
            "cand_devops_mid",  # no python
            "cand_frontend_senior",
            "cand_frontend_mid",
            "cand_frontend_junior",
        ),
        must_not_top=frozenset(
            {"cand_frontend_mid", "cand_frontend_junior", "cand_devops_mid"}
        ),
        notes="Python + SQL + data libraries; experience breaks ties.",
    ),
]
