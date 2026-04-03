"""
Создание superadmin аккаунта.

Использование:
  PYTHONPATH=. python backend/seed_admin.py <email> <password> <name>

Пример:
  PYTHONPATH=. python backend/seed_admin.py admin@topmashina.ru mypassword "Слава"
"""
import asyncio
import sys

import bcrypt

from backend.db.connection import get_pool
from backend.db.admin_queries import get_admin_by_email, create_admin_user


async def main():
    if len(sys.argv) < 4:
        print("Использование: python backend/seed_admin.py <email> <password> <name>")
        sys.exit(1)

    email, password, name = sys.argv[1], sys.argv[2], sys.argv[3]

    await get_pool()

    existing = await get_admin_by_email(email)
    if existing:
        print(f"Админ с email {email} уже существует")
        sys.exit(1)

    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    admin = await create_admin_user(email, password_hash, name, "superadmin")
    print(f"Superadmin создан: id={admin['id']}, email={admin['email']}, role=superadmin")


asyncio.run(main())
