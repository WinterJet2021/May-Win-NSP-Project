// backend/src/routes/users.rs

use axum::{extract::{Path, Query, State}, Json};
use serde::Deserialize;
use sqlx::{query_as, query};
use crate::{AppState, models::User};
use super::internal_error;

#[derive(Deserialize)]
pub struct ListUsersQ {
    pub organization_id: Option<i64>,
    pub limit: Option<i64>,
    pub offset: Option<i64>,
}

#[derive(Deserialize)]
pub struct CreateUserBody {
    pub organization_id: i64,
    pub full_name: String,
    pub nickname: Option<String>,
    pub role: String,
    pub password_hash: String,
}

#[derive(Deserialize)]
pub struct PatchUserBody {
    pub full_name: Option<String>,
    pub nickname: Option<String>,
    pub role: Option<String>,
    pub password_hash: Option<String>,
    pub is_active: Option<bool>,
}

pub async fn create_user(
    State(state): State<AppState>,
    Json(b): Json<CreateUserBody>,
) -> Result<Json<User>, (axum::http::StatusCode, String)> {
    let row = query_as::<_, User>(
        r#"
        INSERT INTO public.users(organization_id, full_name, nickname, role, password_hash)
        VALUES ($1,$2,$3,$4,$5)
        RETURNING user_id, organization_id, full_name, nickname, role, password_hash, is_active, created_at, updated_at
        "#
    )
    .bind(b.organization_id).bind(b.full_name).bind(b.nickname)
    .bind(b.role).bind(b.password_hash)
    .fetch_one(&state.pool).await.map_err(internal_error)?;
    Ok(Json(row))
}

pub async fn list_users(
    State(state): State<AppState>,
    Query(q): Query<ListUsersQ>,
) -> Result<Json<Vec<User>>, (axum::http::StatusCode, String)> {
    let limit = q.limit.unwrap_or(50).clamp(1, 500);
    let offset = q.offset.unwrap_or(0).max(0);

    let rows = if let Some(org) = q.organization_id {
        query_as::<_, User>(r#"SELECT * FROM public.users WHERE organization_id=$1 ORDER BY user_id DESC LIMIT $2 OFFSET $3"#)
            .bind(org).bind(limit).bind(offset)
            .fetch_all(&state.pool).await.map_err(internal_error)?
    } else {
        query_as::<_, User>(r#"SELECT * FROM public.users ORDER BY user_id DESC LIMIT $1 OFFSET $2"#)
            .bind(limit).bind(offset)
            .fetch_all(&state.pool).await.map_err(internal_error)?
    };
    Ok(Json(rows))
}

pub async fn patch_user(
    State(state): State<AppState>,
    Path(id): Path<i64>,
    Json(b): Json<PatchUserBody>,
) -> Result<Json<User>, (axum::http::StatusCode, String)> {
    let row = query_as::<_, User>(
        r#"
        UPDATE public.users SET
          full_name = COALESCE($2, full_name),
          nickname = COALESCE($3, nickname),
          role = COALESCE($4, role),
          password_hash = COALESCE($5, password_hash),
          is_active = COALESCE($6, is_active),
          updated_at = now()
        WHERE user_id = $1
        RETURNING user_id, organization_id, full_name, nickname, role, password_hash, is_active, created_at, updated_at
        "#
    )
    .bind(id).bind(b.full_name).bind(b.nickname).bind(b.role).bind(b.password_hash).bind(b.is_active)
    .fetch_one(&state.pool).await.map_err(internal_error)?;
    Ok(Json(row))
}

pub async fn delete_user(
    State(state): State<AppState>,
    Path(id): Path<i64>,
) -> Result<Json<serde_json::Value>, (axum::http::StatusCode, String)> {
    let res = query(r#"DELETE FROM public.users WHERE user_id=$1"#)
        .bind(id).execute(&state.pool).await.map_err(internal_error)?;
    Ok(Json(serde_json::json!({"deleted": res.rows_affected() > 0})))
}
