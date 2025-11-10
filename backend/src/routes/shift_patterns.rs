// backend/src/routes/shift_patterns.rs

use axum::{extract::{Path, State}, Json};
use chrono::NaiveTime;
use serde::Deserialize;
use sqlx::{query_as, query};
use crate::{AppState, models::ShiftPattern};
use super::internal_error;

#[derive(Deserialize)]
pub struct CreateShiftBody {
    pub name: String,
    pub start_time: NaiveTime,
    pub end_time: NaiveTime,
    pub is_night: bool,
    #[serde(default)] pub required_skills: serde_json::Value,
}

pub async fn create_shift(
    State(state): State<AppState>,
    Path(unit_id): Path<i64>,
    Json(b): Json<CreateShiftBody>,
) -> Result<Json<ShiftPattern>, (axum::http::StatusCode, String)> {
    let row = query_as::<_, ShiftPattern>(
        r#"
        INSERT INTO public.shift_patterns(unit_id, name, start_time, end_time, is_night, required_skills)
        VALUES ($1,$2,$3,$4,$5,$6)
        RETURNING shift_pattern_id, unit_id, name, start_time, end_time, is_night, required_skills
        "#
    )
    .bind(unit_id).bind(b.name).bind(b.start_time).bind(b.end_time).bind(b.is_night).bind(b.required_skills)
    .fetch_one(&state.pool).await.map_err(internal_error)?;
    Ok(Json(row))
}

pub async fn list_shifts_by_unit(
    State(state): State<AppState>,
    Path(unit_id): Path<i64>,
) -> Result<Json<Vec<ShiftPattern>>, (axum::http::StatusCode, String)> {
    let rows = query_as::<_, ShiftPattern>(
        r#"SELECT * FROM public.shift_patterns WHERE unit_id=$1 ORDER BY shift_pattern_id"#)
        .bind(unit_id).fetch_all(&state.pool).await.map_err(internal_error)?;
    Ok(Json(rows))
}

#[derive(Deserialize)]
pub struct PatchShiftBody {
    pub name: Option<String>,
    pub start_time: Option<NaiveTime>,
    pub end_time: Option<NaiveTime>,
    pub is_night: Option<bool>,
    pub required_skills: Option<serde_json::Value>,
}

pub async fn patch_shift(
    State(state): State<AppState>,
    Path(id): Path<i64>,
    Json(b): Json<PatchShiftBody>,
) -> Result<Json<ShiftPattern>, (axum::http::StatusCode, String)> {
    let row = query_as::<_, ShiftPattern>(
        r#"
        UPDATE public.shift_patterns SET
          name = COALESCE($2, name),
          start_time = COALESCE($3, start_time),
          end_time = COALESCE($4, end_time),
          is_night = COALESCE($5, is_night),
          required_skills = COALESCE($6, required_skills)
        WHERE shift_pattern_id = $1
        RETURNING shift_pattern_id, unit_id, name, start_time, end_time, is_night, required_skills
        "#
    )
    .bind(id).bind(b.name).bind(b.start_time).bind(b.end_time).bind(b.is_night).bind(b.required_skills)
    .fetch_one(&state.pool).await.map_err(internal_error)?;
    Ok(Json(row))
}

pub async fn delete_shift(
    State(state): State<AppState>,
    Path(id): Path<i64>,
) -> Result<Json<serde_json::Value>, (axum::http::StatusCode, String)> {
    let res = query(r#"DELETE FROM public.shift_patterns WHERE shift_pattern_id=$1"#)
        .bind(id).execute(&state.pool).await.map_err(internal_error)?;
    Ok(Json(serde_json::json!({"deleted": res.rows_affected() > 0})))
}
