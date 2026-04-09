import asyncpg
from backend.db.connection import get_pool


# ──────────────────────────────────────────────
# Users
# ──────────────────────────────────────────────

async def get_user_by_id(user_id: int) -> asyncpg.Record | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM users WHERE id = $1", user_id)


async def get_user_by_email(email: str) -> asyncpg.Record | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM users WHERE email = $1", email)


async def create_user_by_email(email: str, password_hash: str) -> asyncpg.Record:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            """
            INSERT INTO users (email, password_hash, email_verified, applications_balance)
            VALUES ($1, $2, FALSE, 150)
            RETURNING *
            """,
            email, password_hash,
        )


async def verify_user_email(user_id: int) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET email_verified = TRUE WHERE id = $1",
            user_id,
        )


async def update_user_profile(user_id: int, **fields) -> asyncpg.Record | None:
    allowed = {"name", "first_name", "last_name", "phone", "username", "gender"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not updates:
        return await get_user_by_id(user_id)

    set_clause = ", ".join(f"{k} = ${i+2}" for i, k in enumerate(updates))
    values = [user_id] + list(updates.values())

    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            f"UPDATE users SET {set_clause} WHERE id = $1 RETURNING *",
            *values,
        )


async def update_user_password(user_id: int, password_hash: str) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET password_hash = $1 WHERE id = $2",
            password_hash, user_id,
        )


# Для обратной совместимости с ботом (бот использует telegram_id)
async def get_user_by_code(code: str) -> asyncpg.Record | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM users WHERE code = $1", code)


async def get_user_by_telegram_id(telegram_id: int) -> asyncpg.Record | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM users WHERE telegram_id = $1",
            telegram_id,
        )


async def get_user_by_yandex_id(yandex_id: str) -> asyncpg.Record | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM users WHERE yandex_id = $1", yandex_id)


async def create_user_by_yandex(
    yandex_id: str,
    email: str | None,
    first_name: str | None,
    last_name: str | None,
    phone: str | None,
    gender: str | None,
    avatar_url: str | None,
) -> asyncpg.Record:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            """
            INSERT INTO users (yandex_id, email, first_name, last_name, phone, gender, avatar_url,
                               applications_balance, email_verified)
            VALUES ($1, $2::VARCHAR, $3::VARCHAR, $4::VARCHAR, $5::VARCHAR, $6::VARCHAR, $7::VARCHAR, 150, CASE WHEN $2::VARCHAR IS NOT NULL THEN TRUE ELSE FALSE END)
            RETURNING *
            """,
            yandex_id, email, first_name, last_name, phone, gender, avatar_url,
        )


async def link_yandex_to_user(
    user_id: int,
    yandex_id: str,
    first_name: str | None,
    last_name: str | None,
    phone: str | None,
    gender: str | None,
    avatar_url: str | None,
) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE users
            SET yandex_id = $2, first_name = $3, last_name = $4,
                phone = COALESCE(phone, $5), gender = $6, avatar_url = $7
            WHERE id = $1
            """,
            user_id, yandex_id, first_name, last_name, phone, gender, avatar_url,
        )


# ──────────────────────────────────────────────
# Verification Tokens
# ──────────────────────────────────────────────

async def create_verification_token(user_id: int, token: str, token_type: str, expires_at) -> asyncpg.Record:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            """
            INSERT INTO verification_tokens (user_id, token, type, expires_at)
            VALUES ($1, $2, $3, $4)
            RETURNING *
            """,
            user_id, token, token_type, expires_at,
        )


async def get_verification_token(token: str, token_type: str) -> asyncpg.Record | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            """
            SELECT * FROM verification_tokens
            WHERE token = $1 AND type = $2 AND used = FALSE AND expires_at > NOW()
            """,
            token, token_type,
        )


async def mark_token_used(token_id: int) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE verification_tokens SET used = TRUE WHERE id = $1",
            token_id,
        )


# ──────────────────────────────────────────────
# Applications
# ──────────────────────────────────────────────

async def create_application(
    user_id: int,
    site: str,
    region: str | None,
    region_id: int,
    audit: bool,
    keywords_selection: bool,
    google: bool,
    yandex: bool,
    keywords: str | None,
) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO applications
                (user_id, site, region, audit,
                keywords_selection, google, yandex, keywords, status, region_id)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NULL, $9)
            RETURNING *
            """,
            user_id, site, region, audit,
            keywords_selection, google, yandex, keywords, region_id,
        )
        return row


ALLOWED_JSONB_COLUMNS = {"keywords_from_topvizard"}
ALLOWED_FIELDS = {
    "topvizard_id", "topvizard_link", "status",
    "region", "audit", "keywords_from_topvizard",
}


async def update_application(id: int, key: str, value):
    if key not in ALLOWED_FIELDS:
        raise ValueError(f"Invalid field: {key}")

    pool = await get_pool()
    if key in ALLOWED_JSONB_COLUMNS:
        query = f"""
            UPDATE applications SET {key} = $1::jsonb WHERE id = $2 RETURNING *
        """
    else:
        query = f"""
            UPDATE applications SET {key} = $1 WHERE id = $2 RETURNING *
        """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, value, id)
        return row


async def get_user_applications(user_id: int) -> list[asyncpg.Record]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(
            """
            SELECT * FROM applications
            WHERE user_id = $1 AND status IS NOT NULL
            ORDER BY created_at DESC
            """,
            user_id,
        )


async def delete_project(project_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM applications WHERE id = $1", project_id)


async def get_application_by_id(project_id: int) -> asyncpg.Record | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM applications WHERE id = $1",
            project_id,
        )


async def get_application_by_topvizard_id(topvizard_id: int) -> asyncpg.Record | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM applications WHERE topvizard_id = $1",
            str(topvizard_id),
        )


# ──────────────────────────────────────────────
# Balance
# ──────────────────────────────────────────────

async def get_user_balance(user_id: int) -> int | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT applications_balance FROM users WHERE id = $1",
            user_id,
        )
        return row["applications_balance"] if row else None


async def add_user_balance(user_id: int, amount: int) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE users SET applications_balance = applications_balance + $1
            WHERE id = $2 RETURNING applications_balance
            """,
            amount, user_id,
        )
        return row["applications_balance"]


async def deduct_user_balance(user_id: int, amount: int = 1) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE users SET applications_balance = applications_balance - $2
            WHERE id = $1 AND applications_balance >= $2
            RETURNING applications_balance
            """,
            user_id, amount,
        )
        return row is not None


async def set_user_applications_balance(user_id: int, balance: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.execute(
            """
            UPDATE users SET applications_balance = applications_balance + $1
            WHERE id = $2
            """,
            balance, user_id,
        )


# ──────────────────────────────────────────────
# Keywords
# ──────────────────────────────────────────────

async def insert_keywords_for_project(project_id: int, group_id: int, keywords: list[dict]) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.executemany(
            """
            INSERT INTO keywords_applications (keyword_id, name, project_id, group_id)
            VALUES ($1, $2, $3, $4)
            """,
            [(kw["id"], kw["name"], project_id, group_id) for kw in keywords],
        )


async def upsert_keywords_for_project(project_id: int, group_id: int, keywords: list[dict]) -> list[asyncpg.Record]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.executemany(
            """
            INSERT INTO keywords_applications (keyword_id, name, project_id, group_id)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (name, project_id) DO UPDATE
                SET keyword_id = EXCLUDED.keyword_id
            """,
            [(kw["id"], kw["name"], project_id, group_id) for kw in keywords],
        )
        return await conn.fetch(
            "SELECT * FROM keywords_applications WHERE project_id = $1 ORDER BY created_at DESC",
            project_id,
        )


async def update_keywords_for_project(id: str, keyword_id: int, name: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            """
            UPDATE keywords_applications
            SET keyword_id = $1, name = $2
            WHERE id = $3::uuid
            RETURNING *
            """,
            keyword_id, name, id,
        )


async def get_keywords_by_project_id(project_id: int) -> list[asyncpg.Record]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT * FROM keywords_applications WHERE project_id = $1",
            project_id,
        )


async def delete_keywords_by_id(keyword_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM keywords_applications WHERE keyword_id = $1", keyword_id)


async def get_keywords_by_id(keyword_id: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM keywords_applications WHERE id = $1", keyword_id)


# ──────────────────────────────────────────────
# Payments
# ──────────────────────────────────────────────

async def create_payment(payment_id: int, user_id: int, tariff: str, amount: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO payments (payment_id, user_id, tariff, amount)
            VALUES ($1, $2, $3, $4)
            """,
            payment_id, user_id, tariff, amount,
        )


async def get_payment(payment_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM payments WHERE payment_id = $1", payment_id)


async def mark_payment_confirmed(payment_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE payments SET status = 'CONFIRMED', confirmed_at = NOW()
            WHERE payment_id = $1
            """,
            payment_id,
        )
