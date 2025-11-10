// backend/src/routes/scenarios.rs

use axum::{extract::{Path, Query, State}, Json};
use serde::Deserialize;
use sha2::{Digest, Sha256};
use sqlx::{query_as, query};
use crate::{AppState, models::Scenario};
use super::internal_error;

#[derive(Deserialize)]
pub struct CreateScenarioBody {
    pub unit_id: i64,
    pub source: String,                 // "web" | "chatbot" | "csv"
    pub payload: serde_json::Value,     // matches SolveRequest snapshot
    pub created_by: Option<i64>,
}

#[derive(Deserialize)]
pub struct PatchScenarioBody {
    pub status: Option<String>,         // ready|queued|running|succeeded|failed
}

#[derive(Deserialize)]
pub struct ListQ { pub unit_id: Option<i64> }

pub async fn create_scenario(
    State(state): State<AppState>,
    Json(b): Json<CreateScenarioBody>,
) -> Result<Json<Scenario>, (axum::http::StatusCode, String)> {
    // canonical hash of payload
    let bytes = serde_json::to_vec(&b.payload).map_err(internal_error)?;
    let mut hasher = Sha256::new();
    hasher.update(&bytes);
    let input_hash = format!("{:x}", hasher.finalize());

    let row = query_as::<_, Scenario>(
        r#"
        INSERT INTO public.scenarios(unit_id, source, input_hash, payload, status, created_by)
        VALUES ($1,$2,$3,$4,'ready',$5)
        ON CONFLICT (unit_id, input_hash) DO UPDATE SET payload=EXCLUDED.payload, status='ready'
        RETURNING scenario_id, unit_id, source, input_hash, payload, status, created_by, created_at
        "#
    )
    .bind(b.unit_id).bind(b.source).bind(&input_hash).bind(b.payload).bind(b.created_by)
    .fetch_one(&state.pool).await.map_err(internal_error)?;
    Ok(Json(row))
}

pub async fn list_scenarios(
    State(state): State<AppState>,
    Query(q): Query<ListQ>,
) -> Result<Json<Vec<Scenario>>, (axum::http::StatusCode, String)> {
    let rows = if let Some(u) = q.unit_id {
        query_as::<_, Scenario>(r#"SELECT * FROM public.scenarios WHERE unit_id=$1 ORDER BY created_at DESC"#)
            .bind(u).fetch_all(&state.pool).await.map_err(internal_error)?
    } else {
        query_as::<_, Scenario>(r#"SELECT * FROM public.scenarios ORDER BY created_at DESC"#)
            .fetch_all(&state.pool).await.map_err(internal_error)?
    };
    Ok(Json(rows))
}

pub async fn get_scenario(
    State(state): State<AppState>,
    Path(id): Path<i64>,
) -> Result<Json<Scenario>, (axum::http::StatusCode, String)> {
    let row = query_as::<_, Scenario>(r#"SELECT * FROM public.scenarios WHERE scenario_id=$1"#)
        .bind(id).fetch_one(&state.pool).await.map_err(internal_error)?;
    Ok(Json(row))
}

pub async fn patch_scenario(
    State(state): State<AppState>,
    Path(id): Path<i64>,
    Json(b): Json<PatchScenarioBody>,
) -> Result<Json<Scenario>, (axum::http::StatusCode, String)> {
    let row = query_as::<_, Scenario>(
        r#"
        UPDATE public.scenarios SET
          status = COALESCE($2, status)
        WHERE scenario_id = $1
        RETURNING scenario_id, unit_id, source, input_hash, payload, status, created_by, created_at
        "#
    )
    .bind(id).bind(b.status)
    .fetch_one(&state.pool).await.map_err(internal_error)?;
    Ok(Json(row))
}

pub async fn delete_scenario(
    State(state): State<AppState>,
    Path(id): Path<i64>,
) -> Result<Json<serde_json::Value>, (axum::http::StatusCode, String)> {
    let res = query(r#"DELETE FROM public.scenarios WHERE scenario_id=$1"#)
        .bind(id).execute(&state.pool).await.map_err(internal_error)?;
    Ok(Json(serde_json::json!({"deleted": res.rows_affected() > 0})))
}
