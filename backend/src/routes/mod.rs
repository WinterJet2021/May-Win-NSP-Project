use axum::http::StatusCode;

pub mod health;
pub mod organizations;
pub mod sites;
pub mod units;
pub mod users;
pub mod shift_patterns;
pub mod staffs;
pub mod coverage;
pub mod availability;
pub mod preferences;
pub mod policy_sets;
pub mod scenarios;
pub mod solver_runs;
pub mod assignments;
pub mod kpi;

// Common error mapper
pub fn internal_error<E: std::fmt::Display>(e: E) -> (StatusCode, String) {
    (StatusCode::INTERNAL_SERVER_ERROR, format!("internal error: {e}"))
}
