// backend/src/routes/staffs.rs

use axum::{extract::{Path, State}, Json};
use serde::Deserialize;
use sqlx::{query_as, query};
use crate::{AppState, models::Staff};
use super::internal_error;

#[derive(Deserialize)]
pub struct CreateStaffBody {
    pub code: String,
    pub full_name: String,
    pub nickname: Option<String>,
    pub role: Option<String>,
    pub skills: Vec<String>,
    pub contract_type: Option<String>,
    pub max_weekly_hours: Option<i32>,
    pub enabled: Option<bool>,
}

pub async fn create_staff(
    State(state): State<AppState>,
    Path(unit_id): Path<i64>,
    Json(b): Json<CreateStaffBody>,
) -> Result<Json<Staff>, (axum::http::StatusCode, String)> {
    let row = query_as::<_, Staff>(
        r#"
        INSERT INTO public.staffs(unit_id, code, full_name, nickname, role, skills, contract_type, max_weekly_hours, enabled)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8, COALESCE($9, TRUE))
        RETURNING staff_id, unit_id, code, full_name, nickname, role, skills, contract_type, max_weekly_hours, enabled
        "#
    )
    .bind(unit_id).bind(b.code).bind(b.full_name).bind(b.nickname).bind(b.role)
    .bind(b.skills).bind(b.contract_type).bind(b.max_weekly_hours).bind(b.enabled)
    .fetch_one(&state.pool).await.map_err(internal_error)?;
    Ok(Json(row))
}

pub async fn list_staffs_by_unit(
    State(state): State<AppState>,
    Path(unit_id): Path<i64>,
) -> Result<Json<Vec<Staff>>, (axum::http::StatusCode, String)> {
    let rows = query_as::<_, Staff>(
        r#"SELECT * FROM public.staffs WHERE unit_id=$1 ORDER BY code"#)
        .bind(unit_id).fetch_all(&state.pool).await.map_err(internal_error)?;
    Ok(Json(rows))
}

#[derive(Deserialize)]
pub struct PatchStaffBody {
    pub code: Option<String>,
    pub full_name: Option<String>,
    pub nickname: Option<String>,
    pub role: Option<String>,
    pub skills: Option<Vec<String>>,
    pub contract_type: Option<String>,
    pub max_weekly_hours: Option<i32>,
    pub enabled: Option<bool>,
}

pub async fn patch_staff(
    State(state): State<AppState>,
    Path(id): Path<i64>,
    Json(b): Json<PatchStaffBody>,
) -> Result<Json<Staff>, (axum::http::StatusCode, String)> {
    let row = query_as::<_, Staff>(
        r#"
        UPDATE public.staffs SET
          code = COALESCE($2, code),
          full_name = COALESCE($3, full_name),
          nickname = COALESCE($4, nickname),
          role = COALESCE($5, role),
          skills = COALESCE($6, skills),
          contract_type = COALESCE($7, contract_type),
          max_weekly_hours = COALESCE($8, max_weekly_hours),
          enabled = COALESCE($9, enabled)
        WHERE staff_id = $1
        RETURNING staff_id, unit_id, code, full_name, nickname, role, skills, contract_type, max_weekly_hours, enabled
        "#
    )
    .bind(id).bind(b.code).bind(b.full_name).bind(b.nickname).bind(b.role)
    .bind(b.skills).bind(b.contract_type).bind(b.max_weekly_hours).bind(b.enabled)
    .fetch_one(&state.pool).await.map_err(internal_error)?;
    Ok(Json(row))
}

pub async fn delete_staff(
    State(state): State<AppState>,
    Path(id): Path<i64>,
) -> Result<Json<serde_json::Value>, (axum::http::StatusCode, String)> {
    let res = query(r#"DELETE FROM public.staffs WHERE staff_id=$1"#)
        .bind(id).execute(&state.pool).await.map_err(internal_error)?;
    Ok(Json(serde_json::json!({"deleted": res.rows_affected() > 0})))
}
