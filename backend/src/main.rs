// backend/src/main.rs

use std::env;

use axum::{
    routing::{delete, get, patch, post, put},
    Router,
};
use sqlx::{Pool, Postgres};
use tokio::net::TcpListener;
use tower_http::{
    cors::{Any, CorsLayer},
    trace::TraceLayer,
};

mod db;
mod models;
mod routes;

#[derive(Clone)]
pub struct AppState {
    pub pool: Pool<Postgres>,
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    // Load environment from .env if present
    dotenvy::dotenv().ok();

    // Initialize DB pool
    let pool = db::connect().await?;
    let state = AppState { pool };

    // Very permissive CORS for local dev (tighten for prod)
    let cors = CorsLayer::new()
        .allow_origin(Any)
        .allow_methods(Any)
        .allow_headers(Any);

    // Root API router
    let api = Router::new()
        // health
        .route("/health", get(routes::health::health))
        // organizations
        .route(
            "/api/v1/organizations",
            post(routes::organizations::create_org).get(routes::organizations::list_orgs),
        )
        .route(
            "/api/v1/organizations/:id",
            get(routes::organizations::get_org)
                .patch(routes::organizations::patch_org)
                .delete(routes::organizations::delete_org),
        )
        // sites
        .route(
            "/api/v1/organizations/:org_id/sites",
            post(routes::sites::create_site).get(routes::sites::list_sites_for_org),
        )
        .route("/api/v1/organization-sites/:id", delete(routes::sites::delete_site))
        // units
        .route(
            "/api/v1/units",
            post(routes::units::create_unit).get(routes::units::list_units),
        )
        .route(
            "/api/v1/units/:id",
            get(routes::units::get_unit)
                .patch(routes::units::patch_unit)
                .delete(routes::units::delete_unit),
        )
        // users
        .route(
            "/api/v1/users",
            post(routes::users::create_user).get(routes::users::list_users),
        )
        .route(
            "/api/v1/users/:id",
            patch(routes::users::patch_user).delete(routes::users::delete_user),
        )
        // shift patterns
        .route(
            "/api/v1/units/:unit_id/shift-patterns",
            post(routes::shift_patterns::create_shift)
                .get(routes::shift_patterns::list_shifts_by_unit),
        )
        .route(
            "/api/v1/shift-patterns/:id",
            patch(routes::shift_patterns::patch_shift)
                .delete(routes::shift_patterns::delete_shift),
        )
        // staffs
        .route(
            "/api/v1/units/:unit_id/staffs",
            post(routes::staffs::create_staff)
                .get(routes::staffs::list_staffs_by_unit),
        )
        .route(
            "/api/v1/staffs/:id",
            patch(routes::staffs::patch_staff).delete(routes::staffs::delete_staff),
        )
        // coverage
        .route(
            "/api/v1/units/:unit_id/coverage/bulk",
            put(routes::coverage::bulk_upsert_coverage),
        )
        .route(
            "/api/v1/units/:unit_id/coverage",
            get(routes::coverage::list_coverage),
        )
        // availability / preferences
        .route(
            "/api/v1/availability/bulk",
            post(routes::availability::bulk_upsert_availability),
        )
        .route(
            "/api/v1/preferences/bulk",
            post(routes::preferences::bulk_upsert_preferences),
        )
        // policy sets
        .route(
            "/api/v1/units/:unit_id/policy-sets",
            post(routes::policy_sets::create_policy)
                .get(routes::policy_sets::list_policies),
        )
        .route(
            "/api/v1/policy-sets/:id",
            get(routes::policy_sets::get_policy)
                .patch(routes::policy_sets::patch_policy)
                .delete(routes::policy_sets::delete_policy),
        )
        // scenarios
        .route(
            "/api/v1/scenarios",
            post(routes::scenarios::create_scenario).get(routes::scenarios::list_scenarios),
        )
        .route(
            "/api/v1/scenarios/:id",
            get(routes::scenarios::get_scenario)
                .patch(routes::scenarios::patch_scenario)
                .delete(routes::scenarios::delete_scenario),
        )
        // solver runs (+ ingest result)
        .route(
            "/api/v1/solver-runs",
            post(routes::solver_runs::create_run).get(routes::solver_runs::list_runs),
        )
        .route("/api/v1/solver-runs/:id", get(routes::solver_runs::get_run))
        .route(
            "/api/v1/solver-runs/:id/ingest-result",
            post(routes::solver_runs::ingest_result),
        )
        // outputs
        .route("/api/v1/assignments", get(routes::assignments::list_assignments))
        .route("/api/v1/kpi/:solver_run_id", get(routes::kpi::get_kpi))
        // state & middleware
        .with_state(state)
        .layer(cors)
        .layer(TraceLayer::new_for_http());

    // Port (axum 0.7 style)
    let port: u16 = env::var("PORT")
    .ok()
    .and_then(|s| s.parse().ok())
    .unwrap_or(8080); // default 8080

    let addr = format!("0.0.0.0:{port}");
    let listener = TcpListener::bind(&addr).await?;

    let api_base = format!("http://127.0.0.1:{port}");
    println!("✅ PORT={}, using {}", port, addr);
    println!("🚀 API listening on {api_base}");

    axum::serve(listener, api.into_make_service()).await?;
    Ok(())
}
