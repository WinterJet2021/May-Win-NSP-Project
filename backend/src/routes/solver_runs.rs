// backend/src/routes/solver_runs.rs

use axum::{extract::{Path, State}, Json};
use axum::http::StatusCode;
use chrono::NaiveDate;
use serde::{Deserialize, Serialize};
use sqlx::{query, query_as};
use std::collections::HashMap;

use crate::{AppState, models::SolverRun};
use super::internal_error;

// ─────────────────────────────────────────────────────────────────────────────
// Request / Response models
// ─────────────────────────────────────────────────────────────────────────────

#[derive(Deserialize)]
pub struct CreateRunBody {
    pub scenario_id: i64,
    pub policy_set_id: i64,
    pub seed: Option<i32>,
    pub workers: Option<i32>,
    pub code_version: Option<String>,
}

#[derive(Deserialize)]
pub struct ListQ { pub scenario_id: Option<i64> }

// Types to deserialize FastAPI /solve response
#[derive(Deserialize)]
struct SolveAssignment { day: String, shift: String, nurse: String }
#[derive(Deserialize)]
struct SolveUnder { day: String, shift: String, missing: i32 }
#[derive(Deserialize)]
struct SolveNurseStats { nurse: String, assigned_shifts: i32, overtime: i32, nights: i32, satisfaction: i32 }
#[derive(Deserialize)]
struct SolveResponse {
    status: String,
    objective_value: Option<i64>,
    assignments: Vec<SolveAssignment>,
    understaffed: Vec<SolveUnder>,
    nurse_stats: Vec<SolveNurseStats>,
    details: Option<serde_json::Value>,
}

#[derive(Serialize, Deserialize, Clone)]
pub struct IngestAssignmentRow {
    pub day: chrono::NaiveDate,
    pub shift_id: i64,
    pub staff_id: i64,
    pub is_overtime: bool,
    pub source: String,
}

#[derive(Serialize, Deserialize, Clone)]
pub struct IngestKpiRow {
    pub solver_run_id: i64,
    pub avg_satisfaction: i32,
    pub understaff_total: i32,
    pub overtime_total: i32,
    pub night_violations: i32,
    pub senior_coverage_ok: bool,
}

#[derive(Serialize, Deserialize, Clone)]
pub struct IngestBody {
    pub status: String,
    pub wall_time_sec: Option<f64>,
    pub logs_url: Option<String>,
    pub assignments: Vec<IngestAssignmentRow>,
    pub kpi: Option<IngestKpiRow>,
}

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────

fn norm(s: &str) -> String {
    s.trim().to_lowercase()
}

fn parse_day(s: &str) -> Result<NaiveDate, String> {
    NaiveDate::parse_from_str(s, "%Y-%m-%d")
        .or_else(|_| NaiveDate::parse_from_str(s, "%Y/%m/%d"))
        .map_err(|e| format!("invalid date '{}': {}", s, e))
}

// ─────────────────────────────────────────────────────────────────────────────
// Handlers
// ─────────────────────────────────────────────────────────────────────────────

/// POST /api/v1/solver-runs
pub async fn create_run(
    State(state): State<AppState>,
    Json(b): Json<CreateRunBody>,
) -> Result<Json<SolverRun>, (StatusCode, String)> {
    // 0) Basic environment
    let fastapi_base = std::env::var("FASTAPI_SOLVER_URL")
        .unwrap_or_else(|_| "http://127.0.0.1:8000".into());
    let rust_api_base = std::env::var("RUST_API_BASE")
        .unwrap_or_else(|_| "http://127.0.0.1:8080".into());

    // 1) Mark scenario queued
    query(r#"UPDATE public.scenarios SET status='queued' WHERE scenario_id=$1"#)
        .bind(b.scenario_id)
        .execute(&state.pool)
        .await
        .map_err(internal_error)?;

    // 2) Create run (status=queued)
    let run = query_as::<_, SolverRun>(
        r#"
        INSERT INTO public.solver_runs
          (scenario_id, policy_set_id, status, seed, workers, code_version, started_at)
        VALUES
          ($1,$2,'queued',$3,$4,$5, now())
        RETURNING solver_run_id, scenario_id, policy_set_id, status, seed, workers,
                  wall_time_sec, code_version, logs_url, started_at, finished_at
        "#
    )
    .bind(b.scenario_id)
    .bind(b.policy_set_id)
    .bind(b.seed)
    .bind(b.workers)
    .bind(b.code_version)
    .fetch_one(&state.pool)
    .await
    .map_err(internal_error)?;

    // 3) Load the exact SolveRequest from scenarios.payload + unit_id for mapping
    let (payload, unit_id): (serde_json::Value, i64) = sqlx::query_as(
        r#"SELECT payload, unit_id FROM public.scenarios WHERE scenario_id=$1"#
    )
    .bind(b.scenario_id)
    .fetch_one(&state.pool)
    .await
    .map_err(internal_error)?;

    // 4) Call FastAPI /solve
    let solve_url = format!("{}/solve", fastapi_base);
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(120))
        .build()
        .map_err(|e| internal_error(format!("reqwest build error: {e}")))?;

    let started = std::time::Instant::now();
    let solve_resp: SolveResponse = client.post(&solve_url)
        .json(&payload)
        .send().await.map_err(internal_error)?
        .error_for_status().map_err(internal_error)?
        .json().await.map_err(internal_error)?;
    let wall = started.elapsed().as_secs_f64();

    // 5) Build mapping: shift name -> id (case/space-insensitive)
    let shift_rows = query_as::<_, (i64, String)>(
        r#"SELECT shift_pattern_id, name FROM public.shift_patterns WHERE unit_id=$1"#
    )
    .bind(unit_id)
    .fetch_all(&state.pool)
    .await
    .map_err(internal_error)?;

    let mut shift_id_by_name: HashMap<String, i64> = HashMap::new();
    for (id, name) in shift_rows {
        shift_id_by_name.insert(norm(&name), id);
    }

    // 6) Build mapping: staff (code and full_name) -> id (case/space-insensitive)
    let staff_rows = query_as::<_, (i64, Option<String>, String)>(
        r#"SELECT staff_id, code, full_name FROM public.staffs WHERE unit_id=$1"#
    )
    .bind(unit_id)
    .fetch_all(&state.pool)
    .await
    .map_err(internal_error)?;

    let mut staff_id_by_key: HashMap<String, i64> = HashMap::new();
    for (sid, code_opt, full_name) in staff_rows {
        if let Some(code) = code_opt {
            staff_id_by_key.insert(norm(&code), sid);
        }
        staff_id_by_key.insert(norm(&full_name), sid);
    }

    // 7) Map solver assignments → DB ids (fail fast with readable errors)
    let mut ingest_rows: Vec<IngestAssignmentRow> = Vec::with_capacity(solve_resp.assignments.len());
    for a in &solve_resp.assignments {
        let day = parse_day(&a.day).map_err(|e| (StatusCode::BAD_REQUEST, e))?;

        let shift_key = norm(&a.shift);
        let staff_key = norm(&a.nurse);

        let sid = shift_id_by_name.get(&shift_key).copied().ok_or_else(|| {
            (StatusCode::BAD_REQUEST, format!("Unknown shift name from solver: '{}'", a.shift))
        })?;

        let stid = staff_id_by_key.get(&staff_key).copied().ok_or_else(|| {
            (StatusCode::BAD_REQUEST, format!("Unknown nurse identifier from solver: '{}'", a.nurse))
        })?;

        ingest_rows.push(IngestAssignmentRow {
            day,
            shift_id: sid,
            staff_id: stid,
            is_overtime: false,
            source: "MODEL".to_string(),
        });
    }

    // 8) Compute simple KPI
    let avg_sat = if solve_resp.nurse_stats.is_empty() {
        0
    } else {
        (solve_resp.nurse_stats.iter().map(|s| s.satisfaction).sum::<i32>() as f64
            / solve_resp.nurse_stats.len() as f64).round() as i32
    };

    let kpi = IngestKpiRow {
        solver_run_id: run.solver_run_id,
        avg_satisfaction: avg_sat,
        understaff_total: solve_resp.understaffed.iter().map(|u| u.missing.max(0)).sum(),
        overtime_total: solve_resp.nurse_stats.iter().map(|s| s.overtime.max(0)).sum(),
        night_violations: 0,
        senior_coverage_ok: true,
    };

    // 9) Call our own ingestion route (keeps insert logic centralized)
    let ingest_url = format!("{}/api/v1/solver-runs/{}/ingest-result", rust_api_base, run.solver_run_id);
    let ingest = IngestBody {
        status: if solve_resp.status.to_lowercase().contains("fail") { "failed".into() } else { "succeeded".into() },
        wall_time_sec: Some(wall),
        logs_url: None,
        assignments: ingest_rows,
        kpi: Some(kpi),
    };

    client.post(&ingest_url)
        .json(&ingest)
        .send().await.map_err(internal_error)?
        .error_for_status().map_err(internal_error)?;

    // 10) Return refreshed row
    let run2 = query_as::<_, SolverRun>(
        r#"SELECT * FROM public.solver_runs WHERE solver_run_id=$1"#
    )
    .bind(run.solver_run_id)
    .fetch_one(&state.pool)
    .await
    .map_err(internal_error)?;

    Ok(Json(run2))
}

// GET /api/v1/solver-runs
pub async fn list_runs(
    State(state): State<AppState>,
) -> Result<Json<Vec<SolverRun>>, (StatusCode, String)> {
    let rows = query_as::<_, SolverRun>(
        r#"SELECT * FROM public.solver_runs ORDER BY solver_run_id DESC"#
    )
    .fetch_all(&state.pool)
    .await
    .map_err(internal_error)?;
    Ok(Json(rows))
}

// GET /api/v1/solver-runs/:id
pub async fn get_run(
    State(state): State<AppState>,
    Path(id): Path<i64>,
) -> Result<Json<SolverRun>, (StatusCode, String)> {
    let row = query_as::<_, SolverRun>(
        r#"SELECT * FROM public.solver_runs WHERE solver_run_id=$1"#
    )
    .bind(id)
    .fetch_one(&state.pool)
    .await
    .map_err(internal_error)?;
    Ok(Json(row))
}

// POST /api/v1/solver-runs/:id/ingest-result
pub async fn ingest_result(
    State(state): State<AppState>,
    Path(id): Path<i64>,
    Json(body): Json<IngestBody>,
) -> Result<Json<serde_json::Value>, (StatusCode, String)> {
    let mut tx = state.pool.begin().await.map_err(internal_error)?;

    // Update run status + meta
    query(
        r#"
        UPDATE public.solver_runs
           SET status = $2,
               wall_time_sec = COALESCE($3, wall_time_sec),
               logs_url = COALESCE($4, logs_url),
               finished_at = now()
         WHERE solver_run_id = $1
        "#
    )
    .bind(id)
    .bind(&body.status)
    .bind(body.wall_time_sec)
    .bind(&body.logs_url)
    .execute(&mut *tx)
    .await
    .map_err(internal_error)?;

    // Insert assignments
    for a in &body.assignments {
        query(
            r#"
            INSERT INTO public.assignments
                (solver_run_id, day, shift_id, staff_id, is_overtime, source)
            VALUES ($1,$2,$3,$4,$5,$6)
            ON CONFLICT DO NOTHING
            "#
        )
        .bind(id)
        .bind(a.day)
        .bind(a.shift_id)
        .bind(a.staff_id)
        .bind(a.is_overtime)
        .bind(&a.source)
        .execute(&mut *tx)
        .await
        .map_err(internal_error)?;
    }

    // Insert KPI (if provided)
    if let Some(k) = &body.kpi {
        query(
            r#"
            INSERT INTO public.kpi
                (solver_run_id, avg_satisfaction, understaff_total, overtime_total,
                 night_violations, senior_coverage_ok)
            VALUES ($1,$2,$3,$4,$5,$6)
            ON CONFLICT (solver_run_id) DO UPDATE
               SET avg_satisfaction = EXCLUDED.avg_satisfaction,
                   understaff_total = EXCLUDED.understaff_total,
                   overtime_total  = EXCLUDED.overtime_total,
                   night_violations = EXCLUDED.night_violations,
                   senior_coverage_ok = EXCLUDED.senior_coverage_ok
            "#
        )
        .bind(id)
        .bind(k.avg_satisfaction)
        .bind(k.understaff_total)
        .bind(k.overtime_total)
        .bind(k.night_violations)
        .bind(k.senior_coverage_ok)
        .execute(&mut *tx)
        .await
        .map_err(internal_error)?;
    }

    tx.commit().await.map_err(internal_error)?;

    Ok(Json(serde_json::json!({ "ok": true, "solver_run_id": id })))
}
