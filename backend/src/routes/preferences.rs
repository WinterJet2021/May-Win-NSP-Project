// backend/src/routes/preferences.rs

use axum::{extract::State, Json};
use chrono::NaiveDate;
use serde::Deserialize;
use sqlx::query;
use crate::AppState;
use super::internal_error;

#[derive(Deserialize)]
pub struct PreferenceUpsertItem {
    pub staff_id: i64,
    pub day: NaiveDate,
    pub shift_id: i64,
    pub penalty: i32, // >= 0
}

pub async fn bulk_upsert_preferences(
    State(state): State<AppState>,
    Json(items): Json<Vec<PreferenceUpsertItem>>,
) -> Result<Json<serde_json::Value>, (axum::http::StatusCode, String)> {
    let mut tx = state.pool.begin().await.map_err(internal_error)?;

    for it in &items {
        query(
            r#"
            INSERT INTO public.preferences(staff_id, day, shift_id, penalty)
            VALUES ($1,$2,$3,$4)
            ON CONFLICT (staff_id, day, shift_id)
            DO UPDATE SET penalty = EXCLUDED.penalty
            "#
        )
        .bind(it.staff_id)
        .bind(it.day)
        .bind(it.shift_id)
        .bind(it.penalty)
        .execute(&mut *tx).await.map_err(internal_error)?;
    }

    tx.commit().await.map_err(internal_error)?;
    Ok(Json(serde_json::json!({"upserted": true, "count": items.len()})))
}
