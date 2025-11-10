// backend/src/routes/availability.rs

use axum::{extract::State, Json};
use chrono::NaiveDate;
use serde::Deserialize;
use sqlx::query;
use crate::AppState;
use super::internal_error;

#[derive(Deserialize)]
pub struct AvailabilityUpsertItem {
    pub staff_id: i64,
    pub day: NaiveDate,
    pub shift_id: i64,
    pub value: i32, // 0 or 1
}

pub async fn bulk_upsert_availability(
    State(state): State<AppState>,
    Json(items): Json<Vec<AvailabilityUpsertItem>>,
) -> Result<Json<serde_json::Value>, (axum::http::StatusCode, String)> {
    let mut tx = state.pool.begin().await.map_err(internal_error)?;

    // iterate by reference to avoid moving `items`
    for it in &items {
        query(
            r#"
            INSERT INTO public.availability(staff_id, day, shift_id, value)
            VALUES ($1,$2,$3,$4)
            ON CONFLICT (staff_id, day, shift_id)
            DO UPDATE SET value = EXCLUDED.value
            "#
        )
        .bind(it.staff_id)
        .bind(it.day)
        .bind(it.shift_id)
        .bind(it.value)
        .execute(&mut *tx).await.map_err(internal_error)?;
    }

    tx.commit().await.map_err(internal_error)?;
    Ok(Json(serde_json::json!({"upserted": true, "count": items.len()})))
}
