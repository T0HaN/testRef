from contextlib import asynccontextmanager
from datetime import datetime
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from markupsafe import Markup, escape

from config import settings
from dependencies import templates
from utils import (
    init_static_data,
    init_redis, close_redis,
    init_monsters_table, init_scenes_table
)

# Импорт наших модулей
from routers import auth, characters, master, player, websockets, dashboard, profile, creator, market

import utils

# === Lifespan ===
@asynccontextmanager
async def lifespan(app: FastAPI):
    # === Startup ===
    print("\n" + "=" * 50)
    print("🚀 Запуск D&D Character Manager")
    print("=" * 50)

    # Инициализация Redis
    print("\n🔌 Подключение к Redis...")
    await init_redis()
    print("✅ Redis подключен")

    # Загрузка статических данных
    print("\n📦 Загрузка статических данных...")
    init_static_data()

    # Инициализация таблицы монстров (создаст таблицу, если её нет)
    print("\n🗃️ Инициализация таблицы монстров...")
    init_monsters_table()

    # Таблица сцен используется VTT и должна существовать до первого запроса.
    init_scenes_table()

    # print(utils.EQUIPMENT_DATA)  # Закомментировано, чтобы не спамить в консоль при запуске

    print("\n" + "=" * 50)
    print("✨ Приложение готово к работе")
    print("=" * 50 + "\n")

    yield

    # === Shutdown ===
    print("\n🛑 Завершение работы приложения...")
    await close_redis()
    print("🔌 Отключено от Redis")
    print("👋 До свидания!")


# === Инициализация приложения ===
app = FastAPI(
    title="D&D Character Manager",
    description="Приложение для управления персонажами D&D 5e",
    version="1.0.0",
    lifespan=lifespan
)

# Монтирование статики
app.mount("/static", StaticFiles(directory=str(settings.STATIC_DIR)), name="static")


# === Middleware ===
def _normalized_origin(value: str) -> str:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return ""
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"


def _request_origin_is_allowed(request: Request) -> bool:
    """Проверяет Origin/Referer для cookie-аутентифицированных изменяющих запросов."""
    source = request.headers.get("origin") or request.headers.get("referer")
    if not source:
        return False

    source_origin = _normalized_origin(source)
    request_origin = _normalized_origin(str(request.base_url))
    configured = {_normalized_origin(settings.APP_BASE_URL)}
    configured.update(
        _normalized_origin(origin.strip())
        for origin in settings.WS_ALLOWED_ORIGINS.split(",")
        if origin.strip()
    )
    configured.discard("")
    return source_origin == request_origin or source_origin in configured


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    if (
        request.method not in {"GET", "HEAD", "OPTIONS", "TRACE"}
        and request.cookies.get("session")
        and not _request_origin_is_allowed(request)
    ):
        return JSONResponse({"detail": "Cross-site request rejected"}, status_code=403)

    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if request.cookies.get("session") and not request.url.path.startswith(("/static/", "/media/")):
        response.headers.setdefault("Cache-Control", "private, no-store")
    if request.url.scheme == "https":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


# === Jinja2 Фильтры ===
def nl2br_filter(s: str):
    """Экранирует HTML и заменяет переносы строк на <br>"""
    return (escape(str(s)).replace('\n', '<br>\n') if s else '')


def timestamp_to_date(ts):
    """Преобразует Unix-timestamp в читаемую дату"""
    try:
        return datetime.fromtimestamp(int(ts)).strftime('%d.%m.%Y %H:%M')
    except (ValueError, TypeError, OSError):
        return '—'


templates.env.filters['nl2br'] = nl2br_filter
templates.env.filters['timestamp_to_date'] = timestamp_to_date


# === Exception Handlers ===
@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    return templates.TemplateResponse(
        request,
        "errors/404.html",
        context={"request": request, "detail": str(request.url)},
        status_code=404,
    )


@app.exception_handler(500)
async def server_error_handler(request: Request, exc):
    return templates.TemplateResponse(
        request,
        "errors/500.html",
        context={"request": request, "detail": str(exc)},
        status_code=500,
    )


@app.exception_handler(403)
async def forbidden_handler(request: Request, exc):
    return templates.TemplateResponse(
        request,
        "errors/403.html",
        context={"request": request},
        status_code=403,
    )


@app.exception_handler(401)
async def unauthorized_handler(request: Request, exc):
    return templates.TemplateResponse(
        request,
        "errors/401.html",
        context={"request": request},
        status_code=401,
    )


@app.exception_handler(503)
async def service_unavailable_handler(request: Request, exc):
    return templates.TemplateResponse(
        request,
        "errors/503.html",
        context={"request": request},
        status_code=503,
    )


# === Подключение Роутеров ===
app.include_router(auth.router)
app.include_router(characters.router)
app.include_router(master.router)
app.include_router(player.router)
app.include_router(websockets.router)
app.include_router(dashboard.router)
app.include_router(profile.profile_router)
app.include_router(creator.creator_router)
app.include_router(market.market_router)

# === Запуск ===
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
