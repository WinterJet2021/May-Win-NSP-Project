// backend/src/routes/assignments.rs

use axum::{extract::{Query, State}, Json};
use serde::Deserialize;
use sqlx::query_as;
use crate::{AppState, models::Assignment};
use super::internal_error; // keep this

#[derive(Deserialize)]
pub struct ListQ {
    pub solver_run_id: i64,
}

pub async fn list_assignments(
    State(state): State<AppState>,
    Query(q): Query<ListQ>,
) -> Result<Json<Vec<Assignment>>, (axum::http::StatusCode, String)> {
    let rows = query_as::<_, Assignment>(
        r#"SELECT assignment_id, solver_run_id, day, shift_id, staff_id, is_overtime, source
           FROM public.assignments WHERE solver_run_id = $1
           ORDER BY day, shift_id"#
    )
    .bind(q.solver_run_id)
    .fetch_all(&state.pool)
    .await
    .map_err(internal_error)?; // ⬅ use the imported name
    Ok(Json(rows))
}
