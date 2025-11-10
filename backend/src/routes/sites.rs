// backend/src/routes/sites.rs

use axum::{extract::{Path, State}, Json};
use serde::{Deserialize, Serialize};
use sqlx::{query_as, query, FromRow}; // ⬅ add FromRow
use crate::{AppState, models::OrganizationSite};
use super::internal_error;

#[derive(Deserialize)]
pub struct CreateSiteBody {
    pub name: String,
    pub time_zone: String,
}

pub async fn create_site(
    State(state): State<AppState>,
    Path(org_id): Path<i64>,
    Json(body): Json<CreateSiteBody>,
) -> Result<Json<OrganizationSite>, (axum::http::StatusCode, String)> {
    let row = query_as::<_, OrganizationSite>(
        r#"
        INSERT INTO public.organization_site(organization_id, name, time_zone)
        VALUES ($1,$2,$3)
        RETURNING organization_site_id, organization_id, name, time_zone
        "#
    )
    .bind(org_id)
    .bind(&body.name)
    .bind(&body.time_zone)
    .fetch_one(&state.pool).await.map_err(internal_error)?;
    Ok(Json(row))
}

#[derive(Serialize, FromRow)] // ⬅ derive FromRow
pub struct SiteLite {
    pub organization_site_id: i64,
    pub name: String,
    pub time_zone: String,
}

pub async fn list_sites_for_org(
    State(state): State<AppState>,
    Path(org_id): Path<i64>,
) -> Result<Json<Vec<SiteLite>>, (axum::http::StatusCode, String)> {
    let rows = query_as::<_, SiteLite>(
        r#"
        SELECT organization_site_id, name, time_zone
        FROM public.organization_site
        WHERE organization_id = $1
        ORDER BY organization_site_id DESC
        "#
    )
    .bind(org_id)
    .fetch_all(&state.pool).await.map_err(internal_error)?;
    Ok(Json(rows))
}

pub async fn delete_site(
    State(state): State<AppState>,
    Path(id): Path<i64>,
) -> Result<Json<serde_json::Value>, (axum::http::StatusCode, String)> {
    let res = query(r#"DELETE FROM public.organization_site WHERE organization_site_id = $1"#)
        .bind(id)
        .execute(&state.pool).await.map_err(internal_error)?;
    Ok(Json(serde_json::json!({ "deleted": res.rows_affected() > 0 })))
}
