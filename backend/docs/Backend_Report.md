# MayWin Nurse Scheduling Platform: Backend Architecture, API Flow & Pipeline Summary

## 1. System Overview

The **MayWin Nurse Scheduling Platform (NSP)** backend is a modular, service-oriented system built with **Rust (Axum)** for core orchestration and **Python (FastAPI)** for solver computation. It manages hospital organizational data, shift structures, staff information, scheduling policies, and automated roster generation.

---

## 2. High-Level Architecture

```
[Frontend / Postman / Admin Client]
                |
                v
        [Axum REST API (Rust)]
                |
     ┌──────────┴──────────┐
     v                     v
[PostgreSQL DB]     [FastAPI Solver Service]
(SQLx ORM)           (OR-Tools optimization)
                           ^
                           |
                  FASTAPI_SOLVER_URL (e.g. http://172.27.0.1:8000)
```

### Core Components

| Component          | Technology       | Role                                                                           |
| ------------------ | ---------------- | ------------------------------------------------------------------------------ |
| **Axum API**       | Rust, Axum, SQLx | Primary REST layer, database orchestration, validation, persistence            |
| **PostgreSQL**     | SQL              | Stores organizations, units, shifts, staff, policies, scenarios, runs, results |
| **FastAPI Solver** | Python, OR-Tools | Executes constraint optimization, returns assignments & KPIs                   |
| **.env**           | dotenvy          | Environment configuration (DB URL, ports, solver endpoint)                     |

---

## 3. System Flow

### **Step-by-Step Process**

1. **Tenancy Setup** – Create Organization → Site → Unit (wards)
2. **Operational Setup** – Define Shift Patterns, Add Staff, and Upsert Coverage requirements.
3. **Policy Configuration** – Create Policy Sets specifying hard rules & soft constraint weights.
4. **Scenario Creation** – Upload scenario payload with nurses, days, shifts, demand, and preferences.
5. **Solver Execution** – Axum sends scenario + policy to FastAPI `/solve`, waits for output.
6. **Results Storage** – Assignments & KPI metrics persisted into PostgreSQL.
7. **Visualization / Retrieval** – Users or dashboards fetch final rosters and KPI results.

---

## 4. API Flow Summary

### **1. Organization & Site Setup**

* `POST /api/v1/organizations` → create organization
* `POST /api/v1/organizations/{org_id}/sites` → create site with timezone

### **2. Unit Creation**

* `POST /api/v1/units` → create working unit (ICU, ER, etc.)

### **3. Shift Patterns**

* `POST /api/v1/units/{unit_id}/shift-patterns`

```json
{
  "name": "Morning",
  "start_time": "07:00:00",
  "end_time": "15:00:00",
  "is_night": false
}
```

**Response:** `{ shift_pattern_id, unit_id, name, start_time, end_time, is_night }`

### **4. Staff Management**

* `POST /api/v1/units/{unit_id}/staffs`

```json
{
  "code": "N001",
  "full_name": "Nurse 001",
  "role": "RN",
  "skills": ["RN"],
  "contract_type": "fulltime",
  "max_weekly_hours": 40,
  "enabled": true
}
```

### **5. Coverage (Demand)**

* `PUT /api/v1/units/{unit_id}/coverage/bulk`

```json
[
  { "day": "2025-11-10", "shift_id": 10, "required_count": 1 },
  { "day": "2025-11-11", "shift_id": 11, "required_count": 1 }
]
```

### **6. Policy Definition**

* `POST /api/v1/units/{unit_id}/policy-sets`

```json
{
  "name": "default",
  "version": "v2",
  "weights": {
    "understaff_penalty": 80,
    "overtime_penalty": 15
  },
  "hard_rules": {
    "max_consecutive_nights": 2,
    "min_rest_hours": 12
  }
}
```

### **7. Scenario Creation**

* `POST /api/v1/scenarios`

```json
{
  "unit_id": 8,
  "source": "web",
  "payload": {
    "nurses": ["N001", "N002", "N003"],
    "days": ["2025-11-10", "2025-11-11"],
    "shifts": ["Morning", "Evening", "Night"],
    "demand": {
      "2025-11-10": {"Morning": 1, "Evening": 1, "Night": 1},
      "2025-11-11": {"Morning": 1, "Evening": 1, "Night": 1}
    }
  }
}
```

### **8. Solver Run Trigger**

* `POST /api/v1/solver-runs`

```json
{
  "scenario_id": 4,
  "policy_set_id": 8,
  "seed": 42,
  "workers": 4
}
```

### **9. Output Retrieval**

* `GET /api/v1/assignments?solver_run_id=39`
* `GET /api/v1/kpi/39`

**Example Result:**

```json
{
  "solver_run_id": 39,
  "avg_satisfaction": 80,
  "understaff_total": 0,
  "overtime_total": 4,
  "night_violations": 0
}
```

---

## 5. Database Model Overview

| Table               | Key Fields                                                      | Notes                      |
| ------------------- | --------------------------------------------------------------- | -------------------------- |
| `organizations`     | `organization_id`                                               | Root entity                |
| `organization_site` | `organization_site_id`, `organization_id`                       | Location + timezone        |
| `units`             | `unit_id`, `organization_id`, `site_id`                         | Ward or department         |
| `shift_patterns`    | `shift_pattern_id`, `unit_id`                                   | Start/end/is_night         |
| `staffs`            | `staff_id`, `unit_id`                                           | Nurse metadata             |
| `coverage`          | `day`, `shift_id`, `required_count`                             | Daily staffing requirement |
| `policy_sets`       | `policy_set_id`, `unit_id`                                      | Scheduling weights/rules   |
| `scenarios`         | `scenario_id`, `unit_id`                                        | Input payload JSON         |
| `solver_runs`       | `solver_run_id`, `scenario_id`, `policy_set_id`                 | Execution record           |
| `assignments`       | `assignment_id`, `solver_run_id`, `staff_id`, `day`, `shift_id` | Final roster               |
| `kpi`               | `solver_run_id`, `avg_satisfaction`, `overtime_total`, ...      | Metrics summary            |

---

## 6. Backend Pipeline Summary

| Stage              | Module                                | Description                                      |
| ------------------ | ------------------------------------- | ------------------------------------------------ |
| **Input**          | `/organizations`, `/units`, `/staffs` | Administrative setup                             |
| **Constraints**    | `/coverage`, `/policy-sets`           | Demand and policy definition                     |
| **Scenario Build** | `/scenarios`                          | Combines inputs into a solver-ready JSON payload |
| **Optimization**   | `/solver-runs` → FastAPI `/solve`     | Executes CP-SAT model using OR-Tools             |
| **Results**        | `/assignments`, `/kpi/{run_id}`       | Returns schedules and performance metrics        |

---

## 7. Environment & Networking

* `.env` defines:

  ```bash
  DATABASE_URL=postgres://postgres:maywin12345@localhost:5432/maywin
  PORT=8080
  FASTAPI_SOLVER_URL=http://172.27.0.1:8000
  ```
* `172.27.0.1` is the Windows gateway IP used by WSL to reach FastAPI.
* Restart Axum server after `.env` edits to reload configuration.

---

## 8. Example End-to-End Run

| Step | Command Summary         | Output                         |
| ---- | ----------------------- | ------------------------------ |
| 1    | Create org/site/unit    | IDs: 11, 5, 8                  |
| 2    | Define shifts           | IDs: 10, 11, 12                |
| 3    | Add staff               | IDs: 9, 10, 11                 |
| 4    | Upsert coverage         | 3 records                      |
| 5    | Create policy           | policy_set_id = 8              |
| 6    | Create scenario         | scenario_id = 4                |
| 7    | Run solver              | solver_run_id = 39 → succeeded |
| 8    | Fetch assignments & KPI | valid schedule + KPI metrics   |

---

## 9. Key Insights & Best Practices

* Use `required_count` (not `required`) in coverage.
* Ensure `is_night` is included for overnight shifts.
* Always use WSL gateway IP for FastAPI connectivity.
* Duplicate `(unit_id, name, version)` in `policy_sets` yields HTTP 400.
* Keep policies versioned and immutable for reproducibility.

---

## 10. Next Steps

* Generate public API documentation (Swagger or Redoc from OpenAPI spec).
* Automate seed scripts for organizations, sites, and units.
* Add authentication middleware (JWT/role-based).
* Implement async task queue for solver dispatching.

---

**Status:** Backend pipeline validated end-to-end (Run #39 succeeded)

**Author:** Chirayu Sukhum
**Project:** MayWin Nurse Scheduling Platform (URD Year 2)
