"""Queries for the `partners` table (see migration 016_create_partners)."""
import re
import asyncpg

from backend.db.connection import get_pool


# ──────────────────────────────────────────────
# Slug helpers
# ──────────────────────────────────────────────

# Basic Russian → Latin transliteration. Keeps slugs URL-safe and readable.
_RU_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def _transliterate(text: str) -> str:
    result = []
    for ch in text:
        lower = ch.lower()
        if lower in _RU_TRANSLIT:
            result.append(_RU_TRANSLIT[lower])
        else:
            result.append(ch)
    return "".join(result)


def slugify(text: str) -> str:
    """Transliterate Russian, lowercase, replace non-alnum with dashes."""
    if not text:
        return ""
    text = _transliterate(text).lower()
    # replace any sequence of non-alphanumeric with '-'
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = text.strip("-")
    return text or "partner"


async def _slug_exists(conn, slug: str, exclude_id: int | None = None) -> bool:
    if exclude_id is not None:
        row = await conn.fetchrow(
            "SELECT 1 FROM partners WHERE slug = $1 AND id <> $2", slug, exclude_id
        )
    else:
        row = await conn.fetchrow("SELECT 1 FROM partners WHERE slug = $1", slug)
    return row is not None


async def _unique_slug(conn, base: str, exclude_id: int | None = None) -> str:
    base = base or "partner"
    candidate = base
    i = 2
    while await _slug_exists(conn, candidate, exclude_id=exclude_id):
        candidate = f"{base}-{i}"
        i += 1
    return candidate


# ──────────────────────────────────────────────
# Reads
# ──────────────────────────────────────────────

async def get_active_partners() -> list[asyncpg.Record]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(
            """
            SELECT *
            FROM partners
            WHERE is_active = TRUE
            ORDER BY sort_order ASC, id ASC
            """
        )


async def get_all_partners() -> list[asyncpg.Record]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT * FROM partners ORDER BY sort_order ASC, id ASC"
        )


async def get_partner_by_id(partner_id: int) -> asyncpg.Record | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM partners WHERE id = $1", partner_id)


async def get_partner_by_slug(slug: str) -> asyncpg.Record | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM partners WHERE slug = $1", slug)


# ──────────────────────────────────────────────
# Writes
# ──────────────────────────────────────────────

_CREATE_FIELDS = {
    "name", "slug", "logo_url", "short_description", "full_description",
    "website_url", "sort_order", "is_active",
}

_UPDATE_FIELDS = {
    "name", "slug", "logo_url", "short_description", "full_description",
    "website_url", "sort_order", "is_active",
}


async def create_partner(data: dict) -> asyncpg.Record:
    """Create a partner. If `slug` is missing/empty, it will be auto-generated
    from `name` (transliterated + slugified, guaranteed unique).
    """
    name = data.get("name")
    if not name:
        raise ValueError("name is required")
    if not data.get("logo_url"):
        raise ValueError("logo_url is required")
    if not data.get("short_description"):
        raise ValueError("short_description is required")
    if not data.get("full_description"):
        raise ValueError("full_description is required")

    pool = await get_pool()
    async with pool.acquire() as conn:
        slug = (data.get("slug") or "").strip()
        if slug:
            slug = slugify(slug)
        if not slug:
            slug = slugify(name)
        slug = await _unique_slug(conn, slug)

        return await conn.fetchrow(
            """
            INSERT INTO partners (
                slug, name, logo_url, short_description, full_description,
                website_url, sort_order, is_active
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING *
            """,
            slug,
            name,
            data["logo_url"],
            data["short_description"],
            data["full_description"],
            data.get("website_url"),
            data.get("sort_order", 0) or 0,
            data.get("is_active", True) if data.get("is_active") is not None else True,
        )


async def update_partner(partner_id: int, data: dict) -> asyncpg.Record | None:
    """Update fields that are present in `data` (non-None). Returns the updated row or None."""
    updates: dict = {k: v for k, v in data.items() if k in _UPDATE_FIELDS and v is not None}
    if not updates:
        return await get_partner_by_id(partner_id)

    pool = await get_pool()
    async with pool.acquire() as conn:
        # Handle slug uniqueness / regeneration.
        if "slug" in updates:
            slug = slugify(str(updates["slug"]).strip())
            if not slug:
                slug = slugify(updates.get("name") or "")
            updates["slug"] = await _unique_slug(conn, slug, exclude_id=partner_id)

        set_parts = []
        values: list = []
        for i, (k, v) in enumerate(updates.items(), start=2):
            set_parts.append(f"{k} = ${i}")
            values.append(v)
        set_parts.append("updated_at = NOW()")
        set_clause = ", ".join(set_parts)

        return await conn.fetchrow(
            f"UPDATE partners SET {set_clause} WHERE id = $1 RETURNING *",
            partner_id, *values,
        )


async def delete_partner(partner_id: int) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute("DELETE FROM partners WHERE id = $1", partner_id)
        # result example: "DELETE 1"
        try:
            return int(result.split()[-1]) > 0
        except (ValueError, IndexError):
            return False
