import asyncpg
from backend.db.connection import get_pool


# ──────────────────────────────────────────────
# Admin Users
# ──────────────────────────────────────────────

async def get_admin_by_email(email: str) -> asyncpg.Record | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM admin_users WHERE email = $1 AND is_active = TRUE", email
        )


async def get_admin_by_id(admin_id: int) -> asyncpg.Record | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM admin_users WHERE id = $1 AND is_active = TRUE", admin_id
        )


async def create_admin_user(email: str, password_hash: str, name: str, role: str) -> asyncpg.Record:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            """
            INSERT INTO admin_users (email, password_hash, name, role)
            VALUES ($1, $2, $3, $4::admin_role)
            RETURNING *
            """,
            email, password_hash, name, role,
        )


async def get_all_admins() -> list[asyncpg.Record]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT id, email, name, role, is_active, created_at FROM admin_users ORDER BY created_at DESC"
        )


async def deactivate_admin(admin_id: int) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE admin_users SET is_active = FALSE WHERE id = $1", admin_id
        )


# ──────────────────────────────────────────────
# Admin Invites
# ──────────────────────────────────────────────

async def create_admin_invite(email: str, role: str, token: str, invited_by: int, expires_at) -> asyncpg.Record:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            """
            INSERT INTO admin_invites (email, role, token, invited_by, expires_at)
            VALUES ($1, $2::admin_role, $3, $4, $5)
            RETURNING *
            """,
            email, role, token, invited_by, expires_at,
        )


async def get_admin_invite(token: str) -> asyncpg.Record | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            """
            SELECT * FROM admin_invites
            WHERE token = $1 AND used = FALSE AND expires_at > NOW()
            """,
            token,
        )


async def mark_invite_used(invite_id: int) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE admin_invites SET used = TRUE WHERE id = $1", invite_id
        )


# ──────────────────────────────────────────────
# Clients (users table)
# ──────────────────────────────────────────────

async def get_clients(limit: int = 50, offset: int = 0, search: str | None = None) -> list[asyncpg.Record]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        if search:
            return await conn.fetch(
                """
                SELECT id, email, name, phone, telegram_username, applications_balance,
                       email_verified, created_at
                FROM users
                WHERE email ILIKE $1 OR name ILIKE $1 OR phone ILIKE $1
                ORDER BY created_at DESC
                LIMIT $2 OFFSET $3
                """,
                f"%{search}%", limit, offset,
            )
        return await conn.fetch(
            """
            SELECT id, email, name, phone, telegram_username, applications_balance,
                   email_verified, created_at
            FROM users
            ORDER BY created_at DESC
            LIMIT $1 OFFSET $2
            """,
            limit, offset,
        )


async def get_clients_count(search: str | None = None) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        if search:
            row = await conn.fetchrow(
                "SELECT COUNT(*) FROM users WHERE email ILIKE $1 OR name ILIKE $1 OR phone ILIKE $1",
                f"%{search}%",
            )
        else:
            row = await conn.fetchrow("SELECT COUNT(*) FROM users")
        return row["count"]


async def get_client_detail(client_id: int) -> asyncpg.Record | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            """
            SELECT id, email, name, phone, telegram_username, applications_balance,
                   email_verified, created_at
            FROM users WHERE id = $1
            """,
            client_id,
        )


async def delete_client(client_id: int) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Удаляем связанные данные, потом юзера
        await conn.execute("DELETE FROM keywords_applications WHERE project_id IN (SELECT id FROM applications WHERE user_id = $1)", client_id)
        await conn.execute("DELETE FROM applications WHERE user_id = $1", client_id)
        await conn.execute("DELETE FROM payments WHERE user_id = $1", client_id)
        await conn.execute("DELETE FROM verification_tokens WHERE user_id = $1", client_id)
        await conn.execute("DELETE FROM users WHERE id = $1", client_id)


async def update_client(client_id: int, **fields) -> asyncpg.Record | None:
    allowed = {"name", "phone", "telegram_username"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not updates:
        return await get_client_detail(client_id)

    set_clause = ", ".join(f"{k} = ${i+2}" for i, k in enumerate(updates))
    values = [client_id] + list(updates.values())

    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            f"UPDATE users SET {set_clause} WHERE id = $1 RETURNING *",
            *values,
        )


# ──────────────────────────────────────────────
# Applications (admin view)
# ──────────────────────────────────────────────

async def get_all_applications(
    limit: int = 50, offset: int = 0, status: str | None = None
) -> list[asyncpg.Record]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        if status == "pending":
            return await conn.fetch(
                """
                SELECT a.*, u.email as client_email, u.name as client_name,
                       am.name as manager_name
                FROM applications a
                LEFT JOIN users u ON a.user_id = u.id
                LEFT JOIN admin_users am ON a.manager_id = am.id
                WHERE a.status IS NULL
                ORDER BY a.created_at DESC
                LIMIT $1 OFFSET $2
                """,
                limit, offset,
            )
        elif status:
            return await conn.fetch(
                """
                SELECT a.*, u.email as client_email, u.name as client_name,
                       am.name as manager_name
                FROM applications a
                LEFT JOIN users u ON a.user_id = u.id
                LEFT JOIN admin_users am ON a.manager_id = am.id
                WHERE a.status = $1::application_status
                ORDER BY a.created_at DESC
                LIMIT $2 OFFSET $3
                """,
                status, limit, offset,
            )
        return await conn.fetch(
            """
            SELECT a.*, u.email as client_email, u.name as client_name,
                   am.name as manager_name
            FROM applications a
            LEFT JOIN users u ON a.user_id = u.id
            LEFT JOIN admin_users am ON a.manager_id = am.id
            ORDER BY a.created_at DESC
            LIMIT $1 OFFSET $2
            """,
            limit, offset,
        )


async def get_applications_count(status: str | None = None) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        if status == "pending":
            row = await conn.fetchrow("SELECT COUNT(*) FROM applications WHERE status IS NULL")
        elif status:
            row = await conn.fetchrow(
                "SELECT COUNT(*) FROM applications WHERE status = $1::application_status", status
            )
        else:
            row = await conn.fetchrow("SELECT COUNT(*) FROM applications")
        return row["count"]


async def get_application_detail(app_id: int) -> asyncpg.Record | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            """
            SELECT a.*, u.email as client_email, u.name as client_name,
                   am.name as manager_name
            FROM applications a
            LEFT JOIN users u ON a.user_id = u.id
            LEFT JOIN admin_users am ON a.manager_id = am.id
            WHERE a.id = $1
            """,
            app_id,
        )


async def update_application_status(app_id: int, status: str) -> asyncpg.Record | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "UPDATE applications SET status = $1::application_status WHERE id = $2 RETURNING *",
            status, app_id,
        )


async def assign_manager(app_id: int, manager_id: int) -> asyncpg.Record | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "UPDATE applications SET manager_id = $1 WHERE id = $2 RETURNING *",
            manager_id, app_id,
        )


# ──────────────────────────────────────────────
# Client projects (admin view)
# ──────────────────────────────────────────────

async def get_client_applications(client_id: int) -> list[asyncpg.Record]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(
            """
            SELECT a.*, am.name as manager_name
            FROM applications a
            LEFT JOIN admin_users am ON a.manager_id = am.id
            WHERE a.user_id = $1
            ORDER BY a.created_at DESC
            """,
            client_id,
        )


async def get_client_payments(client_id: int) -> list[asyncpg.Record]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT * FROM payments WHERE user_id = $1 ORDER BY created_at DESC",
            client_id,
        )


async def admin_update_application(app_id: int, **fields) -> asyncpg.Record | None:
    allowed = {"site", "region", "region_id", "keywords", "audit", "google", "yandex", "keywords_selection", "total_visits"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not updates:
        return await get_application_detail(app_id)

    set_clause = ", ".join(f"{k} = ${i+2}" for i, k in enumerate(updates))
    values = [app_id] + list(updates.values())

    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            f"UPDATE applications SET {set_clause} WHERE id = $1 RETURNING *",
            *values,
        )


# ──────────────────────────────────────────────
# Dashboard stats
# ──────────────────────────────────────────────

async def get_dashboard_stats() -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        clients = await conn.fetchrow("SELECT COUNT(*) FROM users")
        pending = await conn.fetchrow("SELECT COUNT(*) FROM applications WHERE status IS NULL")
        total_apps = await conn.fetchrow("SELECT COUNT(*) FROM applications")
        payments = await conn.fetchrow(
            "SELECT COALESCE(SUM(amount), 0) as total, COUNT(*) as count FROM payments WHERE status = 'CONFIRMED'"
        )
        return {
            "clients_count": clients["count"],
            "pending_applications": pending["count"],
            "total_applications": total_apps["count"],
            "total_revenue": payments["total"],
            "confirmed_payments": payments["count"],
        }


# ──────────────────────────────────────────────
# Bot Tasks
# ──────────────────────────────────────────────

async def get_bot_tasks_by_application(application_id: int) -> list[asyncpg.Record]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(
            """
            SELECT * FROM bot_tasks
            WHERE application_id = $1
            ORDER BY created_at DESC
            """,
            application_id,
        )


async def get_bot_task_by_id(task_id: int) -> asyncpg.Record | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM bot_tasks WHERE id = $1", task_id
        )


async def create_bot_task(
    application_id: int,
    target_site: str,
    keyword: str,
    daily_visit_target: int,
    total_visit_target: int,
    proxy_url: str | None = None,
) -> asyncpg.Record:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            """
            INSERT INTO bot_tasks (application_id, target_site, keyword, daily_visit_target, total_visit_target, proxy_url)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING *
            """,
            application_id, target_site, keyword, daily_visit_target, total_visit_target, proxy_url,
        )


async def create_bot_tasks_batch(tasks_data: list[tuple]) -> None:
    """Пакетное создание задач"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.executemany(
            """
            INSERT INTO bot_tasks (application_id, target_site, keyword, daily_visit_target, total_visit_target, proxy_url)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            tasks_data
        )


async def update_bot_task_pause(task_id: int, is_paused: bool) -> asyncpg.Record | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "UPDATE bot_tasks SET is_paused = $1, updated_at = NOW() WHERE id = $2 RETURNING *",
            is_paused, task_id,
        )


async def update_bot_task_proxy(task_id: int, proxy_url: str) -> asyncpg.Record | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "UPDATE bot_tasks SET proxy_url = $1, updated_at = NOW() WHERE id = $2 RETURNING *",
            proxy_url, task_id,
        )


async def delete_bot_task(task_id: int) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM bot_tasks WHERE id = $1", task_id)


# ──────────────────────────────────────────────
# Project Proxies
# ──────────────────────────────────────────────

async def get_project_proxies(application_id: int) -> list[asyncpg.Record]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT * FROM project_proxies WHERE application_id = $1 ORDER BY created_at DESC",
            application_id,
        )


async def get_project_proxy_by_id(proxy_id: int) -> asyncpg.Record | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM project_proxies WHERE id = $1", proxy_id
        )


async def create_project_proxy(application_id: int, proxy_url: str) -> asyncpg.Record:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            """
            INSERT INTO project_proxies (application_id, proxy_url)
            VALUES ($1, $2)
            RETURNING *
            """,
            application_id, proxy_url,
        )


async def update_project_proxy(proxy_id: int, proxy_url: str) -> asyncpg.Record | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "UPDATE project_proxies SET proxy_url = $1 WHERE id = $2 RETURNING *",
            proxy_url, proxy_id,
        )


async def delete_project_proxy(proxy_id: int) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM project_proxies WHERE id = $1", proxy_id)


async def get_random_project_proxy(application_id: int) -> asyncpg.Record | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM project_proxies WHERE application_id = $1 ORDER BY RANDOM() LIMIT 1",
            application_id,
        )