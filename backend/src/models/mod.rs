// backend/src/models/mod.rs

use chrono::{DateTime, NaiveDate, NaiveTime, Utc};
use serde::{Deserialize, Serialize};
use sqlx::FromRow;

// ───────────────────────────────────────
// Core tenancy
// ───────────────────────────────────────
#[derive(Debug, Serialize, Deserialize, FromRow)]
pub struct Organization {
    pub organization_id: i64,
    pub name: String,
    pub plan: String,
    pub status: String,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

#[derive(Debug, Serialize, Deserialize, FromRow)]
pub struct OrganizationSite {
    pub organization_site_id: i64,
    pub organization_id: i64,
    pub name: String,
    pub time_zone: String,
}

#[derive(Debug, Serialize, Deserialize, FromRow)]
pub struct Unit {
    pub unit_id: i64,
    pub organization_id: i64,
    pub site_id: Option<i64>,
    pub name: String,
    pub code: String,
    pub time_zone: String,
}

// ───────────────────────────────────────
// Users (simple RBAC role string)
// ───────────────────────────────────────
#[derive(Debug, Serialize, Deserialize, FromRow)]
pub struct User {
    pub user_id: i64,
    pub organization_id: i64,
    pub full_name: String,
    pub nickname: Option<String>,
    pub role: String,
    pub password_hash: String,
    pub is_active: bool,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

// ───────────────────────────────────────
// Reference data: Shift patterns & Staffs
// ───────────────────────────────────────
#[derive(Debug, Serialize, Deserialize, FromRow)]
pub struct ShiftPattern {
    pub shift_pattern_id: i64,
    pub unit_id: i64,
    pub name: String,
    pub start_time: NaiveTime,
    pub end_time: NaiveTime,
    pub is_night: bool,
    pub required_skills: serde_json::Value, // jsonb
}

#[derive(Debug, Serialize, Deserialize, FromRow)]
pub struct Staff {
    pub staff_id: i64,
    pub unit_id: i64,
    pub code: String,
    pub full_name: String,
    pub nickname: Option<String>,
    pub role: Option<String>,
    pub skills: Vec<String>,                 // text[]
    pub contract_type: Option<String>,
    pub max_weekly_hours: Option<i32>,
    pub enabled: bool,
}

// ───────────────────────────────────────
// Planning inputs
// ───────────────────────────────────────
#[derive(Debug, Serialize, Deserialize, FromRow)]
pub struct CoverageRequirement {
    pub coverage_requirement_id: i64,
    pub unit_id: i64,
    pub day: NaiveDate,
    pub shift_id: i64,            // FK → shift_patterns
    pub required_count: i32,
    pub required_skill: serde_json::Value, // jsonb
}

#[derive(Debug, Serialize, Deserialize, FromRow)]
pub struct Availability {
    pub availability_id: i64,
    pub staff_id: i64,
    pub day: NaiveDate,
    pub shift_id: i64,
    pub value: i32,               // 0/1
}

#[derive(Debug, Serialize, Deserialize, FromRow)]
pub struct Preference {
    pub preference_id: i64,
    pub staff_id: i64,
    pub day: NaiveDate,
    pub shift_id: i64,
    pub penalty: i32,             // ≥ 0
}

// ───────────────────────────────────────
// Policies, scenarios, runs, outputs
// ───────────────────────────────────────
#[derive(Debug, Serialize, Deserialize, FromRow)]
pub struct PolicySet {
    pub policy_set_id: i64,
    pub unit_id: i64,
    pub name: String,
    pub version: String,
    pub weights: serde_json::Value,
    pub hard_rules: serde_json::Value,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

#[derive(Debug, Serialize, Deserialize, FromRow)]
pub struct Scenario {
    pub scenario_id: i64,
    pub unit_id: i64,
    pub source: String,           // "web" | "chatbot" | "csv"
    pub input_hash: String,       // SHA256 hex
    pub payload: serde_json::Value,
    pub status: String,           // ready|running|succeeded|failed
    pub created_by: Option<i64>,  // FK → users
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Serialize, Deserialize, FromRow)]
pub struct SolverRun {
    pub solver_run_id: i64,
    pub scenario_id: i64,
    pub policy_set_id: i64,
    pub status: String,           // queued|running|succeeded|failed
    pub seed: Option<i32>,
    pub workers: Option<i32>,
    pub wall_time_sec: Option<f64>,
    pub code_version: Option<String>,
    pub logs_url: Option<String>,
    pub started_at: Option<DateTime<Utc>>,
    pub finished_at: Option<DateTime<Utc>>,
}

#[derive(Debug, Serialize, Deserialize, FromRow)]
pub struct Assignment {
    pub assignment_id: i64,
    pub solver_run_id: i64,
    pub day: NaiveDate,
    pub shift_id: i64,
    pub staff_id: i64,
    pub is_overtime: bool,
    pub source: String,           // MODEL | POSTFILL
}

#[derive(Debug, Serialize, Deserialize, FromRow)]
pub struct Kpi {
    pub solver_run_id: i64,       // PK + FK
    pub avg_satisfaction: i32,    // 0..100
    pub understaff_total: i32,
    pub overtime_total: i32,
    pub night_violations: i32,
    pub senior_coverage_ok: bool,
}

// ───────────────────────────────────────
// DTOs helpful for endpoints
// ───────────────────────────────────────
#[derive(Debug, Serialize, Deserialize)]
pub struct UpsertCount { pub upserted: usize }

#[derive(Debug, Serialize, Deserialize)]
pub struct IngestRunResult {
    pub updated: bool,
    pub assignments_inserted: usize,
    pub kpi_upserted: bool,
}
