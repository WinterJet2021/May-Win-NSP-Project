// backend/src/routes/policy_sets.rs

use axum::{extract::{Path, State}, Json};
use serde::{Deserialize};
use sqlx::{query_as, query};
use axum::http::StatusCode;

use crate::{AppState, models::PolicySet};

// ---------- request/response models ----------

#[derive(Debug, Deserialize)]
pub struct CreatePolicySetBody {
    pub name: String,
    pub version: String,             // e.g., "v1"
    pub weights: serde_json::Value,  // JSON
    pub hard_rules: serde_json::Value,
}

#[derive(Debug, Deserialize)]
pub struct PatchPolicySetBody {
    pub name: Option<String>,
    pub version: Option<String>,
    pub weights: Option<serde_json::Value>,
    pub hard_rules: Option<serde_json::Value>,
}

// ---------- handlers ----------

pub async fn create_policy(
    State(state): State<AppState>,
    Path(unit_id): Path<i64>,
    Json(b): Json<CreatePolicySetBody>,
) -> Result<Json<PolicySet>, (StatusCode, String)> {
    let row = query_as::<_, PolicySet>(
        r#"
        INSERT INTO public.policy_sets (unit_id, name, version, weights, hard_rules)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING policy_set_id, unit_id, name, version, weights, hard_rules, created_at, updated_at
        "#
    )
    .bind(unit_id)
    .bind(&b.name)
    .bind(&b.version)
    .bind(&b.weights)
    .bind(&b.hard_rules)
    .fetch_one(&state.pool)
    .await
    .map_err(internal_error)?;
    Ok(Json(row))
}

pub async fn list_policies(
    State(state): State<AppState>,
    Path(unit_id): Path<i64>,
) -> Result<Json<Vec<PolicySet>>, (StatusCode, String)> {
    let rows = query_as::<_, PolicySet>(
        r#"
        SELECT policy_set_id, unit_id, name, version, weights, hard_rules, created_at, updated_at
        FROM public.policy_sets
        WHERE unit_id = $1
        ORDER BY policy_set_id DESC
        "#
    )
    .bind(unit_id)
    .fetch_all(&state.pool)
    .await
    .map_err(internal_error)?;
    Ok(Json(rows))
}

pub async fn get_policy(
    State(state): State<AppState>,
    Path(id): Path<i64>,
) -> Result<Json<PolicySet>, (StatusCode, String)> {
    let row = query_as::<_, PolicySet>(
        r#"SELECT policy_set_id, unit_id, name, version, weights, hard_rules, created_at, updated_at
           FROM public.policy_sets WHERE policy_set_id = $1"#
    )
    .bind(id)
    .fetch_one(&state.pool)
    .await
    .map_err(internal_error)?;
    Ok(Json(row))
}

pub async fn patch_policy(
    State(state): State<AppState>,
    Path(id): Path<i64>,
    Json(b): Json<PatchPolicySetBody>,
) -> Result<Json<PolicySet>, (StatusCode, String)> {
    let row = query_as::<_, PolicySet>(
        r#"
        UPDATE public.policy_sets
        SET name = COALESCE($2, name),
            version = COALESCE($3, version),
            weights = COALESCE($4, weights),
            hard_rules = COALESCE($5, hard_rules),
            updated_at = now()
        WHERE policy_set_id = $1
        RETURNING policy_set_id, unit_id, name, version, weights, hard_rules, created_at, updated_at
        "#
    )
    .bind(id)
    .bind(&b.name)
    .bind(&b.version)
    .bind(&b.weights)
    .bind(&b.hard_rules)
    .fetch_one(&state.pool)
    .await
    .map_err(internal_error)?;
    Ok(Json(row))
}

pub async fn delete_policy(
    State(state): State<AppState>,
    Path(id): Path<i64>,
) -> Result<Json<serde_json::Value>, (StatusCode, String)> {
    let res = query(r#"DELETE FROM public.policy_sets WHERE policy_set_id = $1"#)
        .bind(id)
        .execute(&state.pool)
        .await
        .map_err(internal_error)?;
    Ok(Json(serde_json::json!({"deleted": res.rows_affected() > 0})))
}

// Reuse your existing error adapter
fn internal_error<E: std::fmt::Display>(e: E) -> (StatusCode, String) {
    (StatusCode::INTERNAL_SERVER_ERROR, format!("{e}"))
}
