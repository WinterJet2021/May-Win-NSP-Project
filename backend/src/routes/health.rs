// backend/src/routes/health.rs

use axum::Json;
use serde::Serialize;

#[derive(Serialize)]
pub struct HealthResp { pub status: &'static str, pub version: &'static str }

pub async fn health() -> Json<HealthResp> {
    Json(HealthResp { status: "ok", version: "v1" })
}