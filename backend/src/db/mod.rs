// backend/src/db/mod.rs

use sqlx::{Pool, Postgres};
use std::env;

pub async fn connect() -> anyhow::Result<Pool<Postgres>> {
    let database_url = env::var("DATABASE_URL")
        .expect("❌ DATABASE_URL must be set in your .env file");

    let pool = sqlx::postgres::PgPoolOptions::new()
        .max_connections(10)
        .connect(&database_url)
        .await?;

    println!("✅ Connected to PostgreSQL");
    Ok(pool)
}
