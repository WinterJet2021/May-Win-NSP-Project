// backend/src/routes/kpi.rs

use axum::{extract::{Path, State}, Json};
use sqlx::query_as;
use crate::{AppState, models::Kpi};
use super::internal_error;

pub async fn get_kpi(
    State(state): State<AppState>,
    Path(run_id): Path<i64>,
) -> Result<Json<Kpi>, (axum::http::StatusCode, String)> {
    let row = query_as::<_, Kpi>(
        r#"SELECT solver_run_id, avg_satisfaction, understaff_total, overtime_total, night_violations, senior_coverage_ok
           FROM public.kpi WHERE solver_run_id=$1"#)
        .bind(run_id).fetch_one(&state.pool).await.map_err(internal_error)?;
    Ok(Json(row))
}
