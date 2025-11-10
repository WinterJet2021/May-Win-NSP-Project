// backend/src/routes/units.rs

use axum::{extract::{Path, Query, State}, Json};
use serde::Deserialize;
use sqlx::{query_as, query};
use crate::AppState;
use crate::models::Unit;
use super::internal_error;

#[derive(Deserialize)]
pub struct ListUnitsQ {
    pub organization_id: Option<i64>,
    pub code: Option<String>,
    pub limit: Option<i64>,
    pub offset: Option<i64>,
}

#[derive(Deserialize)]
pub struct CreateUnitBody {
    pub organization_id: i64,
    pub site_id: Option<i64>,
    pub name: String,
    pub code: String,
    #[serde(default = "default_tz")] pub time_zone: String,
}
fn default_tz() -> String { "Asia/Bangkok".into() }

#[derive(Deserialize)]
pub struct PatchUnitBody {
    pub site_id: Option<i64>,
    pub name: Option<String>,
    pub code: Option<String>,
    pub time_zone: Option<String>,
}

pub async fn list_units(
    State(state): State<AppState>,
    Query(q): Query<ListUnitsQ>,
) -> Result<Json<Vec<Unit>>, (axum::http::StatusCode, String)> {
    let limit = q.limit.unwrap_or(50).clamp(1, 500);
    let offset = q.offset.unwrap_or(0).max(0);

    let rows = match (q.organization_id, q.code) {
        (Some(org), Some(code)) => {
            query_as::<_, Unit>(
                r#"SELECT unit_id, organization_id, site_id, name, code, time_zone
                   FROM public.units
                   WHERE organization_id = $1 AND code = $2
                   ORDER BY unit_id DESC
                   LIMIT $3 OFFSET $4"#)
                .bind(org).bind(code).bind(limit).bind(offset)
                .fetch_all(&state.pool).await.map_err(internal_error)?
        }
        (Some(org), None) => {
            query_as::<_, Unit>(
                r#"SELECT unit_id, organization_id, site_id, name, code, time_zone
                   FROM public.units
                   WHERE organization_id = $1
                   ORDER BY unit_id DESC
                   LIMIT $2 OFFSET $3"#)
                .bind(org).bind(limit).bind(offset)
                .fetch_all(&state.pool).await.map_err(internal_error)?
        }
        _ => {
            query_as::<_, Unit>(
                r#"SELECT unit_id, organization_id, site_id, name, code, time_zone
                   FROM public.units
                   ORDER BY unit_id DESC
                   LIMIT $1 OFFSET $2"#)
                .bind(limit).bind(offset)
                .fetch_all(&state.pool).await.map_err(internal_error)?
        }
    };
    Ok(Json(rows))
}

pub async fn get_unit(
    State(state): State<AppState>,
    Path(id): Path<i64>,
) -> Result<Json<Unit>, (axum::http::StatusCode, String)> {
    let row = query_as::<_, Unit>(
        r#"SELECT unit_id, organization_id, site_id, name, code, time_zone
           FROM public.units WHERE unit_id = $1"#
    )
    .bind(id)
    .fetch_one(&state.pool).await.map_err(internal_error)?;
    Ok(Json(row))
}

pub async fn create_unit(
    State(state): State<AppState>,
    Json(body): Json<CreateUnitBody>,
) -> Result<Json<Unit>, (axum::http::StatusCode, String)> {
    let row = query_as::<_, Unit>(
        r#"
        INSERT INTO public.units (organization_id, site_id, name, code, time_zone)
        VALUES ($1,$2,$3,$4,$5)
        RETURNING unit_id, organization_id, site_id, name, code, time_zone
        "#
    )
    .bind(body.organization_id)
    .bind(body.site_id)
    .bind(body.name)
    .bind(body.code)
    .bind(body.time_zone)
    .fetch_one(&state.pool).await.map_err(internal_error)?;
    Ok(Json(row))
}

pub async fn patch_unit(
    State(state): State<AppState>,
    Path(id): Path<i64>,
    Json(body): Json<PatchUnitBody>,
) -> Result<Json<Unit>, (axum::http::StatusCode, String)> {
    let row = query_as::<_, Unit>(
        r#"
        UPDATE public.units SET
          site_id   = COALESCE($2, site_id),
          name      = COALESCE($3, name),
          code      = COALESCE($4, code),
          time_zone = COALESCE($5, time_zone)
        WHERE unit_id = $1
        RETURNING unit_id, organization_id, site_id, name, code, time_zone
        "#
    )
    .bind(id)
    .bind(body.site_id)
    .bind(body.name)
    .bind(body.code)
    .bind(body.time_zone)
    .fetch_one(&state.pool).await.map_err(internal_error)?;
    Ok(Json(row))
}

pub async fn delete_unit(
    State(state): State<AppState>,
    Path(id): Path<i64>,
) -> Result<Json<serde_json::Value>, (axum::http::StatusCode, String)> {
    let res = query(r#"DELETE FROM public.units WHERE unit_id = $1"#)
        .bind(id)
        .execute(&state.pool).await.map_err(internal_error)?;
    Ok(Json(serde_json::json!({ "deleted": res.rows_affected() > 0 })))
}
