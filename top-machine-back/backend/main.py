import logging

from fastapi import FastAPI
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from backend.db.connection import get_pool, close_pool
from backend.routes import site, auth, balance, payment, keywords, admin_auth, admin_api,bot_api

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    await get_pool()
    yield
    await close_pool()

app = FastAPI(
    title="SEO Bot Backend",
    description="Backend API для SEO Telegram бота",
    version="1.0.0",
    lifespan=lifespan,
    
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # или ["*"] для разработки
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth.router)
app.include_router(balance.router)
app.include_router(site.router)
app.include_router(payment.router)
app.include_router(keywords.router)
app.include_router(admin_auth.router)
app.include_router(admin_api.router)
app.include_router(bot_api.router)


@app.get("/health")
async def health():
    return {"status": "ok"}

# DB_HOST=localhost BOT_INTERNAL_URL=http://localhost:8081/internal/notify uvicorn backend.main:app --reload --host 0.0.0.0 --port 8080
# DB_HOST=localhost PYTHONPATH=. python backend/migrate.py
