// backend/src/routes/coverage.rs

use axum::{extract::{Path, State}, Json};
use chrono::NaiveDate;
use serde::Deserialize;
use sqlx::{query, query_as};
use crate::{AppState, models::CoverageRequirement};
use super::internal_error;

#[derive(Deserialize)]
pub struct CoverageItem {
    pub day: NaiveDate,
    pub shift_id: i64,
    pub required_count: i32,
    #[serde(default)] pub required_skill: serde_json::Value,
}

pub async fn bulk_upsert_coverage(
    State(state): State<AppState>,
    Path(unit_id): Path<i64>,
    Json(items): Json<Vec<CoverageItem>>,
) -> Result<Json<serde_json::Value>, (axum::http::StatusCode, String)> {
    let mut tx = state.pool.begin().await.map_err(internal_error)?;
    for it in items {
        query(
            r#"
            INSERT INTO public.coverage_requirement(unit_id, day, shift_id, required_count, required_skill)
            VALUES ($1,$2,$3,$4,$5)
            ON CONFLICT (unit_id, day, shift_id)
            DO UPDATE SET required_count = EXCLUDED.required_count,
                          required_skill = EXCLUDED.required_skill
            "#
        )
        .bind(unit_id).bind(it.day).bind(it.shift_id).bind(it.required_count).bind(it.required_skill)
        .execute(&mut *tx).await.map_err(internal_error)?;
    }
    tx.commit().await.map_err(internal_error)?;
    Ok(Json(serde_json::json!({"upserted": true})))
}

pub async fn list_coverage(
    State(state): State<AppState>,
    Path(unit_id): Path<i64>,
) -> Result<Json<Vec<CoverageRequirement>>, (axum::http::StatusCode, String)> {
    let rows = query_as::<_, CoverageRequirement>(
        r#"SELECT * FROM public.coverage_requirement WHERE unit_id=$1 ORDER BY day, shift_id"#)
        .bind(unit_id).fetch_all(&state.pool).await.map_err(internal_error)?;
    Ok(Json(rows))
}
