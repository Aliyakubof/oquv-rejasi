# PRD: O'quv Reja Platform

This is the product requirements document — what the tool does, who it's for, and where it's headed. For engineering guidelines, see `GEMINI.md`. For current implementation state, see `status.md`.

---

## 1. Background

Every university in Uzbekistan must create and submit for verification an **O'quv Reja** — a comprehensive curriculum plan for each degree program. This document defines:

- The degree program's official code (*Yo'nalish kodi*), title (*Yo'nalish nomi*), field of knowledge (*Bilim sohasi*), and field of education (*Ta'lim sohasi*).
- The degree type: Bachelor (*Bakalavr*) or Master (*Magistr*).
- The study format: Morning/Full-time (*Kunduzgi*), Evening (*Kechgi*), or External (*Sirtqi* — a compressed format for working adults where courses are taught in one-month blocks per semester over 5 years).
- The program duration (in years).
- The starting academic year (e.g., 2025/2026).
- Every course in the program — mandatory and elective — with its hours, credits, hour-type breakdown, and semester-by-semester distribution.

Once verified, the O'quv Reja is published as a standardized Excel workbook. Universities use this data to calculate total teaching load, determine which teacher specializations are required, and identify which courses need a course syllabus (*O'quv Dastur*) at the start of each academic year.

**The problem:** all of this work — parsing documents, calculating loads, distributing courses to departments and teachers, and pre-filling course syllabi — is currently done by hand. This creates bottlenecks, delays teachers, and introduces errors.

---

## 2. Project Overview

A web platform serving three user roles across the academic workflow:

### 2.1. Academic Office Head (AOH)

The AOH uploads O'quv Reja Excel files. The platform automatically parses each file and extracts:

- General program metadata (code, title, degree type, study format, duration, academic year).
- All mandatory courses with their hours, credits, and semester assignments.
- All elective courses with their hours, credits, and semester assignments.

**Key functions for the AOH:**

- **Filter courses by semester** — quickly see which courses are taught in any given semester.
- **Allocate courses to departments** — assign each course to a department, generating a department-level hours load summary.
- **Semester-level hour division (Semestrovka)** — for courses that span multiple semesters, the platform must split classroom hours across those semesters (see Section 4.2 for the algorithm).
- **Manage reference data** — the AOH maintains the *Bilim sohasi* and *Ta'lim sohasi* lookup tables in the platform's database, adding new entries as needed.
- **Configure teacher types** — the AOH defines categories of teachers (e.g., Professor, Dotsent, Assistant) and sets the minimum annual teaching load for each type.
- **Verify O'quv Dastur submissions** — review, approve, or reject course syllabi submitted by teachers (see Section 2.3).
- **Archive management** — past academic years' O'quv Reja files are archived automatically and remain easily accessible for reference.

### 2.2. Department Head

After the AOH allocates courses, the Department Head can:

- See the department's total teaching load (hours and courses).
- Distribute courses among professors and teachers. A single course can be assigned to multiple teachers, but each teacher must own a different classroom hour type (e.g., one teacher handles lectures, another handles labs). See Section 4.3 for group multiplication rules.
- Track each teacher's load against the minimum threshold for their teacher type (as configured by the AOH), identifying who is over or under the limit.

### 2.3. Professors / Teachers

After the Department Head assigns courses, professors and teachers can:

- View their assigned courses and hours for the upcoming academic year.
- Download a **pre-filled O'quv Dastur** (course syllabus document) for each assigned course.
- Fill in their own data (topics, resources, evaluation criteria) and submit the completed document to the platform.
- If the AOH **approves** the submission, the teacher officially owns the course and its hours.
- If the AOH **rejects** the submission (with feedback), the teacher revises and resubmits.

> **Important:** Assignment by the Department Head does not grant course ownership. Ownership is confirmed only after the teacher submits the O'quv Dastur and the AOH approves it.

> **Note:** When a course has multiple teachers, the O'quv Dastur must be submitted by the lecture owner.

### 2.4. Authentication

All users (AOH, Department Heads, teachers) log in with their **phone number and password**. The platform uses role-based access control: each user is assigned one role that determines which features and data they can access.

---

## 3. Document Specifications

### 3.1. O'quv Reja (Curriculum Plan — Excel)

The O'quv Reja is an Excel workbook that may contain multiple sheets (e.g., separate sheets for different study formats or year-groups). The platform **parses only the first sheet**, which contains the full program and course data for one curriculum variant.

#### 3.1.1. Header: Program Metadata

The top rows of the sheet contain:

| Field | Label in Excel | Format / Notes |
|---|---|---|
| Major code + title | `Ta'lim yo'nalishi` | A single text string: `60310200 - Xalqaro munosabatlar`. The code comes first; once extracted, the platform can derive `Bilim sohasi` and `Ta'lim sohasi` from a pre-populated database. |
| Degree type | `Akademik daraja` | One of: `BAKALAVR` (Bachelor), `MAGISTR` (Master). |
| Program duration | `O'qish muddati` | Integer in years (e.g., `4 yil` → 4). |
| Study format | `Ta'lim shakli` | One of: `kunduzgi` (Morning), `kechgi` (Evening), `sirtqi` (External). |
| Academic year | `O'quv yili` | Format: `2025-2026`. Used to determine which calendar year each semester falls in. |

> **Note:** The metadata labels may have slight formatting variations across files (e.g., `O'qish muddati - 4 yil` vs `O'qish muddati -4 yil`). The parser must handle these differences.

#### 3.1.2. Course Data Structure

Below the header, the sheet contains all courses organized into two sections:

**Section 1 — Mandatory courses (*Majburiy fanlar*)**

The section begins with a row where the first cell contains a value matching one of: `1.00`, `1.0`, `1`, `1,00`, `1,0`. Each subsequent row represents one course until the next section marker.

**Section 2 — Elective courses (*Tanlov fanlar*)**

The section begins with a row where the first cell contains a value matching one of: `2.00`, `2.0`, `2`, `2,00`, `2,0`.

#### 3.1.3. Course Row Layout

Each course occupies one row with the following columns (in approximate order):

| Column | Content | Notes |
|---|---|---|
| 1 | Order number | e.g., `1.01` or `1,01` |
| 2 | Course code | e.g., `O'YT1104` |
| 3 | Course title | e.g., `O'zbekistonning eng yangi tarixi` |
| 4 | Total hours | Classroom + individual study hours. Part of the *Umumiy yuklamaning hajmi* section. |
| 5 | Percentage | The percentage share of the total (may be empty for individual courses). |
| 6 | Total classroom hours (*Jami*) | Part of *Auditoriya mashg'ulotlari*. |
| 7 | Lecture hours (*Ma'ruza*) | |
| 8 | Practice hours (*Amaliy*) | |
| 9 | Lab hours (*Laboratoriya*) | |
| 10 | Seminar hours (*Seminar*) | |
| 11 | Course project (*Kurs ishi*) | Empty if none; contains `KI` or similar marker if the course has a final project. |
| 12 | Independent study hours (*Mustaqil ta'lim*) | |
| 13–N | Weekly hours per semester | One value per semester — how many hours per week this course is taught in that semester. The number of columns varies by study format: **Kunduzgi** = 8 semesters (4 years), **Kechgi** = 8–9 semesters (4–4.5 years), **Sirtqi** = 10 semesters (5 years). An empty cell means the course is not taught in that semester. |
| N+1–M | Credits per semester | Same number of columns as the weekly-hours section. Shows how credits are distributed across semesters. |
| Last | Total credits (*Jami kreditlar*) | Sum of all per-semester credits. |

> **⚠️ Critical parsing note:** The exact column positions may shift between different O'quv Reja files. The parser cannot rely on fixed column indices. It should use the header row labels (`Ma'ruza`, `Amaliy`, `Labaratoriya`, `Seminar`, `Kurs ishi`, etc.) to identify columns dynamically.

#### 3.1.4. Elective Course Specifics

Elective courses follow the same structure as mandatory courses, with one difference: the course code and course title columns are expanded to hold multiple options. For example, elective slot `2.01` might offer two courses. The first row has the primary option's code and title; the row(s) immediately below (with no order number) list the alternative option(s).

All options in an elective slot share the same total hours and credits, but the breakdown across hour types (lecture, practice, lab, seminar) may differ between options.

### 3.2. O'quv Dastur (Course Syllabus — DOCX)

Each teacher who is assigned a course must create and submit this document. The platform pre-fills the first page with data extracted from the O'quv Reja.

#### 3.2.1. Pre-filled Fields

| Field | Source |
|---|---|
| Course title (*Fan nomi*) | From O'quv Reja |
| Study format | `Kunduzgi`, `Kechgi`, or `Sirtqi` |
| *Bilim sohasi* (with code) | Derived from the major code via the database |
| *Ta'lim sohasi* (with code) | Same as above |
| *Ta'lim yo'nalishi* (with code) | From O'quv Reja header |
| Department name | From the platform's department assignment |
| Course code (*Fan kodi*) | From O'quv Reja |
| Academic year(s) | From O'quv Reja. If the course spans multiple years, list them comma-separated. |
| Semester(s) | From O'quv Reja. If the course spans multiple semesters, list them comma-separated. |
| Credits | Per-semester credits (not the total). |
| Course type | `Majburiy` (mandatory) or `Tanlov` (elective) |
| Order number with major code | e.g., `60610100 – 1.19` |
| Hours per week | Weekly contact hours for the relevant semester(s). |
| Hour breakdown | Total hours, lecture, practice, lab, seminar, independent study. |
| Course project indicator | `Kurs ishi` if applicable; `-` if not. |

#### 3.2.2. Pre-generated Tables

The platform also generates empty lesson-planning tables:

- **Classroom lesson tables** — one table per hour type that exists for the course (lecture, practice, lab, seminar). Each table has a number of rows equal to the number of lessons for that hour type. (1 lesson = 2 academic hours, so 30 hours → 15 lesson rows.)
- **Independent study task table** — rows matching the independent study hours allocation.

These tables are left empty for the teacher to fill in with topics, resources, and assessment criteria.

---

## 4. Key Algorithms

### 4.1. Credits-to-Hours Conversion

| Rule | Formula |
|---|---|
| 1 credit = 30 total hours | `total_hours = credits × 30` |
| Classroom hours = 40% of total | `classroom_hours = total_hours × 0.4` |
| Independent study = 60% of total | `independent_hours = total_hours × 0.6` |
| 1 lesson = 2 academic hours | `lessons = hours / 2` |
| 1 semester = 15 teaching weeks | `semester_hours = weekly_hours × 15` |

> **Note:** These percentages are standard, but the actual per-course values are specified in the Excel file and should be used as-is. The 40/60 rule is a general guideline, not an override.

### 4.2. Semestrovka (Multi-Semester Hour Division)

When a course spans multiple semesters, the O'quv Reja specifies how credits are distributed across those semesters, but does **not** divide classroom hours by type (lecture, practice, etc.) per semester. The platform must compute this division.

**Algorithm — for each semester the course is taught in:**

1. Take the semester's credit count from the O'quv Reja.
2. Compute total hours for this semester: `semester_total = credits × 30`.
3. Compute classroom hours for this semester: `semester_classroom = semester_total × 0.4`.
4. Distribute `semester_classroom` across the hour types that exist for this course (lecture, practice, lab, seminar) proportionally based on the course's overall hour-type ratios.
5. Round each hour type to the nearest even number (every value must be divisible by 2, since 1 lesson = 2 hours).
6. Adjust rounding so the sum of all hour types equals `semester_classroom` exactly.

**Worked example:**

A course has 12 total credits split across 2 semesters (6 credits each). The course's total classroom hours are 96, broken down as: 48 lecture, 48 practice.

For semester 1 (6 credits):
- `semester_total = 6 × 30 = 180`
- `semester_classroom = 180 × 0.4 = 72`
- Lecture ratio: 48/96 = 50% → `72 × 0.5 = 36` (divisible by 2 ✓)
- Practice ratio: 48/96 = 50% → `72 × 0.5 = 36` (divisible by 2 ✓)
- Check: 36 + 36 = 72 ✓

Semester 2 follows the same calculation.

### 4.3. Group Multiplication Rule

When a major has multiple student groups, classroom hours are affected:

- **Lectures** are delivered once to all groups combined — lecture hours stay the same regardless of group count.
- **Practice, Lab, and Seminar** sessions are delivered separately to each group — their hours multiply by the number of groups.

**Example:** Major A has **2 groups**. Course B has 24 hours of lectures and 24 hours of lab.

| Hour type | Per-group hours | Groups | Total teaching hours |
|---|---|---|---|
| Lecture | 24 | shared | **24** |
| Lab | 24 | × 2 | **48** |

This multiplication affects the department's and teachers' actual teaching load. The O'quv Reja itself records per-group hours; the platform must apply the multiplier based on the number of groups for that major.

> **Note:** The number of groups per major is data the platform must track. This could come from AOH input or be a separate configuration.

### 4.4. Multi-Teacher Course Assignment

A single course can be assigned to multiple teachers, subject to this constraint: **each teacher must own a different classroom hour type**. For example, one teacher takes the lectures while another takes the labs. Two teachers cannot both be assigned to the lecture portion of the same course.

---

## 5. Open Questions

The following items are not yet fully specified:

1. **Validation rules** — Should the platform run consistency checks after parsing (e.g., verifying that per-semester credits sum to the total, or that classroom hours match stated totals)? If so, should parse errors block the upload or produce warnings?
2. **Group count source** — How does the platform learn the number of student groups per major? Is this entered by the AOH, or imported from another system?
3. **Role management** — Who creates user accounts and assigns roles (AOH, Department Head, Teacher)? Is there a super-admin role?
4. **Notification system** — Should the platform notify teachers when courses are assigned to them, or notify the AOH when an O'quv Dastur is submitted?

---

## 6. Glossary

| Uzbek Term | English | Notes |
|---|---|---|
| O'quv Reja | Curriculum plan | The master Excel document for a degree program. |
| O'quv Dastur | Course syllabus | The DOCX document each teacher submits per course. |
| Majburiy fanlar | Mandatory courses | Required courses in the curriculum. |
| Tanlov fanlar | Elective courses | Course slots where one option is chosen from a list. |
| Auditoriya mashg'ulotlari | Classroom hours | Total in-class contact time. |
| — Ma'ruza | Lecture | |
| — Amaliy (mashg'ulot) | Practice session | |
| — Seminar | Seminar | |
| — Laboratoriya | Lab work | |
| Kurs ishi | Course project | A term-long project, if the course requires one. |
| Mustaqil ta'lim | Independent/self-study | Hours the student works outside the classroom. |
| Semestrovka | Semester-level hour split | The process of dividing total classroom hours across semesters for multi-semester courses. |
| Kunduzgi | Morning / Full-time | Standard daytime education. |
| Kechgi | Evening | Evening classes, typically 4–4.5 years. |
| Sirtqi | External / Part-time | Compressed block format for working adults, 5 years. |
| Bakalavr | Bachelor's degree | |
| Magistr | Master's degree | |
| Kredit | Credit | 1 credit = 30 academic hours. |

---

## 7. Program Metadata Reference

| Field | Example Values |
|---|---|
| Major code (*Yo'nalish kodi*) | `60110200`, `60310200`, `60411100` |
| Degree type (*Akademik daraja*) | `BAKALAVR`, `MAGISTR` |
| Program duration (*O'qish muddati*) | `4 yil` (4 years) |
| Study format (*Ta'lim shakli*) | `kunduzgi`, `kechgi`, `sirtqi` |
| Academic year (*O'quv yili*) | `2025-2026` |
| Qualification (*Kvalifikatsiya*) | `Xalqaro munosabatlar mutaxassisi`, `Xalqaro iqtisodchi` |

---

## 8. Reference Documents

Sample O'quv Reja files and the O'quv Dastur template are located in the `sources/` folder of this repository.