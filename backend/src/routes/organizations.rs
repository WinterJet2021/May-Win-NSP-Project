// backend/src/routes/organizations.rs

use axum::{extract::{Path, Query, State}, Json};
use serde::{Deserialize, Serialize};
use sqlx::{query_as, query};
use crate::AppState;
use crate::models::Organization;
use super::internal_error;

#[derive(Deserialize)]
pub struct ListQ {
    pub status: Option<String>,
    pub limit: Option<i64>,
    pub offset: Option<i64>,
}

#[derive(Deserialize)]
pub struct CreateOrgBody {
    pub name: String,
    #[serde(default = "default_plan")] pub plan: String,
    #[serde(default = "default_status")] pub status: String,
}
fn default_plan() -> String { "standard".into() }
fn default_status() -> String { "active".into() }

#[derive(Deserialize)]
pub struct PatchOrgBody {
    pub name: Option<String>,
    pub plan: Option<String>,
    pub status: Option<String>,
}

#[derive(Serialize)]
pub struct Deleted { pub deleted: bool }

pub async fn list_orgs(
    State(state): State<AppState>,
    Query(q): Query<ListQ>,
) -> Result<Json<Vec<Organization>>, (axum::http::StatusCode, String)> {
    let limit = q.limit.unwrap_or(50).clamp(1, 500);
    let offset = q.offset.unwrap_or(0).max(0);
    let rows = if let Some(st) = q.status {
        query_as::<_, Organization>(
            r#"SELECT * FROM public.organizations WHERE status = $1 ORDER BY created_at DESC LIMIT $2 OFFSET $3"#
        )
        .bind(st)
        .bind(limit)
        .bind(offset)
        .fetch_all(&state.pool).await.map_err(internal_error)?
    } else {
        query_as::<_, Organization>(
            r#"SELECT * FROM public.organizations ORDER BY created_at DESC LIMIT $1 OFFSET $2"#
        )
        .bind(limit)
        .bind(offset)
        .fetch_all(&state.pool).await.map_err(internal_error)?
    };
    Ok(Json(rows))
}

pub async fn get_org(
    State(state): State<AppState>,
    Path(id): Path<i64>,
) -> Result<Json<Organization>, (axum::http::StatusCode, String)> {
    let row = query_as::<_, Organization>(
        r#"SELECT * FROM public.organizations WHERE organization_id = $1"#
    )
    .bind(id)
    .fetch_one(&state.pool).await.map_err(internal_error)?;
    Ok(Json(row))
}

pub async fn create_org(
    State(state): State<AppState>,
    Json(body): Json<CreateOrgBody>,
) -> Result<Json<Organization>, (axum::http::StatusCode, String)> {
    let row = query_as::<_, Organization>(
        r#"
        INSERT INTO public.organizations(name, plan, status)
        VALUES ($1,$2,$3)
        RETURNING organization_id, name, plan, status, created_at, updated_at
        "#
    )
    .bind(&body.name)
    .bind(&body.plan)
    .bind(&body.status)
    .fetch_one(&state.pool).await.map_err(internal_error)?;
    Ok(Json(row))
}

pub async fn patch_org(
    State(state): State<AppState>,
    Path(id): Path<i64>,
    Json(body): Json<PatchOrgBody>,
) -> Result<Json<Organization>, (axum::http::StatusCode, String)> {
    let row = query_as::<_, Organization>(
        r#"
        UPDATE public.organizations SET
            name = COALESCE($2, name),
            plan = COALESCE($3, plan),
            status = COALESCE($4, status),
            updated_at = now()
        WHERE organization_id = $1
        RETURNING organization_id, name, plan, status, created_at, updated_at
        "#
    )
    .bind(id)
    .bind(body.name)
    .bind(body.plan)
    .bind(body.status)
    .fetch_one(&state.pool).await.map_err(internal_error)?;
    Ok(Json(row))
}

pub async fn delete_org(
    State(state): State<AppState>,
    Path(id): Path<i64>,
) -> Result<Json<Deleted>, (axum::http::StatusCode, String)> {
    let res = query(r#"DELETE FROM public.organizations WHERE organization_id = $1"#)
        .bind(id)
        .execute(&state.pool)
        .await
        .map_err(internal_error)?;
    Ok(Json(Deleted { deleted: res.rows_affected() > 0 }))
}
