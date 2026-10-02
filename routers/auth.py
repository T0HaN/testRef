import logging
import re
import secrets
from html import escape

from fastapi import APIRouter, Request, Form, BackgroundTasks, status
from fastapi.responses import HTMLResponse, RedirectResponse
from werkzeug.security import generate_password_hash, check_password_hash
import psycopg2.extras

from utils import get_redis_client, send_email_sync, get_random_quote, get_db_connection
from dependencies import templates, sign_session_data, unsign_session_data
from config import settings

router = APIRouter(tags=["Auth"])
logger = logging.getLogger(__name__)

USERNAME_RE = re.compile(r"^[a-z0-9_]{3,50}$")
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
MIN_PASSWORD_LENGTH = 8
LOGIN_LIMIT = 10
LOGIN_WINDOW_SECONDS = 300
_DUMMY_PASSWORD_HASH = generate_password_hash("not-a-real-password")


def _login_page(request: Request, *, error: str = "", success: str = "", status_code: int = 200):
    return templates.TemplateResponse(request, "login.html", context={
        "error": error or None,
        "success": success or None,
        "quote_text": get_random_quote(),
    }, status_code=status_code)


async def _rate_limited(key: str, limit: int = LOGIN_LIMIT) -> bool:
    """Небольшой распределённый rate limit; при сбое Redis не блокирует вход."""
    try:
        client = get_redis_client()
        redis_key = f"rate_limit:{key}"
        attempts = await client.incr(redis_key)
        if attempts == 1:
            await client.expire(redis_key, LOGIN_WINDOW_SECONDS)
        return attempts > limit
    except Exception:
        logger.exception("Не удалось применить rate limit")
        return False


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Корневой роут: если сессия активна — в единый кабинет, иначе на логин."""
    session_cookie = request.cookies.get('session')
    if session_cookie:
        user = unsign_session_data(session_cookie)
        if user:
            # Все пользователи идут в единый дашборд
            return RedirectResponse(url="/dashboard", status_code=303)

    return RedirectResponse(url="/login", status_code=303)


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Страница входа/регистрации."""
    session_cookie = request.cookies.get('session')
    if session_cookie:
        user = unsign_session_data(session_cookie)
        if user:
            return RedirectResponse(url="/dashboard", status_code=303)

    # Получаем случайную цитату
    quote_text = get_random_quote()

    return templates.TemplateResponse(request, "login.html", context={
        "quote_text": quote_text
    })


@router.post("/login")
async def login(
        request: Request,
        username: str = Form(...),
        password: str = Form(...),
        action: str = Form(...),
        email: str = Form(None)  # 🆕 Добавили опциональное поле email (нужно только для регистрации)
):
    """Обработка авторизации и регистрации через БД."""
    username = username.strip().lower()

    if action not in {"login", "register"}:
        return _login_page(request, error="Некорректное действие", status_code=400)

    client_host = request.client.host if request.client else "unknown"
    rate_key = f"auth:{client_host}:{username[:50]}"
    if await _rate_limited(rate_key, limit=5 if action == "register" else LOGIN_LIMIT):
        return _login_page(
            request,
            error="Слишком много попыток. Повторите через несколько минут.",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    if action == "register" and not USERNAME_RE.fullmatch(username):
        return _login_page(request, error="Логин: 3–50 латинских букв, цифр или _", status_code=400)

    if action == "login" and (not username or len(username) > 200):
        return _login_page(request, error="Некорректный логин", status_code=400)

    if not password or len(password) > 256:
        return _login_page(request, error="Некорректный пароль", status_code=400)

    if action == "register" and len(password) < MIN_PASSWORD_LENGTH:
        return _login_page(request, error="Пароль должен содержать от 8 до 256 символов", status_code=400)

    if action == 'register':
        if not email:
            return templates.TemplateResponse(request, "login.html", context={
                "error": "Для регистрации необходима электронная почта",
                "quote_text": get_random_quote()
            })

        email = email.strip().lower()
        if len(email) > 254 or not EMAIL_RE.fullmatch(email):
            return _login_page(request, error="Некорректный адрес электронной почты", status_code=400)

        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    # 1. Проверяем, заняты ли никнейм или почта
                    cur.execute("SELECT id FROM users WHERE username = %s OR email = %s", (username, email))
                    if cur.fetchone():
                        return templates.TemplateResponse(request, "login.html", context={
                            "error": "Пользователь с таким никнеймом или почтой уже существует",
                            "quote_text": get_random_quote()
                        })

                    # 2. Регистрируем нового пользователя
                    password_hash = generate_password_hash(password)
                    cur.execute(
                        "INSERT INTO users (username, email, password_hash) VALUES (%s, %s, %s)",
                        (username, email, password_hash)
                    )
                    conn.commit()

            return templates.TemplateResponse(request, "login.html", context={
                "success": "Аккаунт создан! Теперь вы можете войти.",
                "quote_text": get_random_quote()
            })

        except Exception:
            logger.exception("Ошибка БД при регистрации")
            return templates.TemplateResponse(request, "login.html", context={
                "error": "Внутренняя ошибка сервера при регистрации",
                "quote_text": get_random_quote()
            })

    else:
        # 🔑 Проверяем логин и пароль
        try:
            with get_db_connection() as conn:
                # Используем RealDictCursor для доступа по ключам
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute("SELECT id, username, password_hash FROM users WHERE username = %s", (username,))
                    user_data = cur.fetchone()

            password_hash = user_data['password_hash'] if user_data else _DUMMY_PASSWORD_HASH
            password_is_valid = check_password_hash(password_hash, password)
            if not user_data or not password_is_valid:
                return templates.TemplateResponse(request, "login.html", context={
                    "error": "Неверный логин или пароль",
                    "quote_text": get_random_quote()
                })

            # Формируем payload сессии (РОЛЬ УБРАНА, ДОБАВЛЕН ID)
            session_payload = {
                'id': user_data['id'],
                'username': user_data['username']
            }

            # 🛡️ Криптографически подписываем данные сессии
            signed_session_cookie = sign_session_data(session_payload)

            response = RedirectResponse(url="/dashboard", status_code=303)

            # Устанавливаем защищённую cookie
            response.set_cookie(
                key="session",
                value=signed_session_cookie,
                httponly=True,
                max_age=86400,  # 24 часа
                secure=settings.SESSION_COOKIE_SECURE,
                samesite="lax"
            )
            try:
                await get_redis_client().delete(f"rate_limit:{rate_key}")
            except Exception:
                logger.exception("Не удалось сбросить rate limit после входа")
            return response

        except Exception:
            logger.exception("Ошибка БД при логине")
            return templates.TemplateResponse(request, "login.html", context={
                "error": "Внутренняя ошибка сервера при авторизации",
                "quote_text": get_random_quote()
            })


@router.post("/logout")
async def logout():
    """Выход из системы и очистка сессии."""
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("session")
    return response


# --- СТРАНИЦА ЗАПРОСА СБРОСА ПАРОЛЯ ---
@router.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(request: Request):
    return templates.TemplateResponse(request, "forgot_password.html", context={})


# --- ОБРАБОТКА ЗАПРОСА СБРОСА ПАРОЛЯ ---
@router.post("/forgot-password")
async def forgot_password_submit(
    request: Request,
    background_tasks: BackgroundTasks,
    email: str = Form(...)
):
    email = email.strip().lower()
    client_host = request.client.host if request.client else "unknown"
    if await _rate_limited(f"password_reset:{client_host}:{email[:254]}", limit=5):
        return templates.TemplateResponse(request, "forgot_password.html", context={
            "info": "Если путник с такой почтой зарегистрирован, свиток с инструкцией отправлен."
        }, status_code=status.HTTP_429_TOO_MANY_REQUESTS)

    if len(email) > 254 or not EMAIL_RE.fullmatch(email):
        # Не раскрываем, существует ли адрес, и сохраняем одинаковый ответ.
        return templates.TemplateResponse(request, "forgot_password.html", context={
            "info": "Если путник с такой почтой зарегистрирован, свиток с инструкцией отправлен."
        })

    # Ищем пользователя в БД
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT id, username, email FROM users WHERE email = %s", (email,))
            user = cur.fetchone()

    if user:
        # Генерируем одноразовый крипто-токен
        token = secrets.token_urlsafe(32)
        r = get_redis_client()
        # Сохраняем связку токен -> user_id на 20 минут (1200 сек)
        await r.setex(f"reset_pwd:{token}", 1200, str(user['id']))

        reset_link = f"{settings.APP_BASE_URL}/reset-password?token={token}"
        
        # HTML письма в стилистике проекта
        email_body = f"""
        <div style="background-color: #141418; color: #e0d4b8; padding: 25px; font-family: Georgia, serif; border: 1px solid #3a352a; border-radius: 8px; max-width: 500px;">
            <h2 style="color: #c9a961; text-transform: uppercase; letter-spacing: 0.1em; margin-top: 0;">Восстановление доступа</h2>
            <p>Приветствуем, путник <strong>{escape(user['username'])}</strong>!</p>
            <p style="color: #a89f8a;">Был получен запрос на сотворение нового тайного ключа (пароля) для вашей летописи в Folio.</p>
            <div style="margin: 25px 0; text-align: center;">
                <a href="{reset_link}" style="background: linear-gradient(145deg, #c9a961, #8b7542); color: #0a0a0c; padding: 12px 20px; text-decoration: none; font-weight: bold; border-radius: 6px; display: inline-block;">
                    🗝️ Сотворить новый пароль
                </a>
            </div>
            <p style="font-size: 0.85rem; color: #8b7542;">Свиток действует 20 минут. Если вы не запрашивали смену ключа, просто проигнорируйте это послание.</p>
        </div>
        """

        background_tasks.add_task(
            send_email_sync,
            to_email=user['email'],
            subject="Восстановление доступа к Folio",
            html_content=email_body
        )

    # Защита от перебора: всегда одинаковый ответ
    return templates.TemplateResponse(request, "forgot_password.html", context={
        "info": "Если путник с такой почтой зарегистрирован, свиток с инструкцией отправлен."
    })


# --- СТРАНИЦА ВВОДА НОВОГО ПАРОЛЯ ---
@router.get("/reset-password", response_class=HTMLResponse)
async def reset_password_page(request: Request, token: str):
    if len(token) > 128:
        return _login_page(request, error="Ссылка восстановления недействительна", status_code=400)
    r = get_redis_client()
    user_id = await r.get(f"reset_pwd:{token}")

    if not user_id:
        return templates.TemplateResponse(request, "login.html", context={
            "error": "Свиток восстановления истлел (ссылка недействительна или устарела)",
            "quote_text": get_random_quote()
        })

    return templates.TemplateResponse(request, "reset_password.html", context={"token": token})


# --- СОХРАНЕНИЕ НОВОГО ПАРОЛЯ ---
@router.post("/reset-password")
async def reset_password_submit(
    request: Request,
    token: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...)
):
    if len(token) > 128:
        return _login_page(request, error="Ссылка восстановления недействительна", status_code=400)
    if new_password != confirm_password:
        return templates.TemplateResponse(request, "reset_password.html", context={
            "token": token,
            "error": "Введённые ключи не совпадают"
        })

    if len(new_password) < MIN_PASSWORD_LENGTH or len(new_password) > 256:
        return templates.TemplateResponse(request, "reset_password.html", context={
            "token": token,
            "error": "Пароль должен содержать от 8 до 256 символов"
        })

    r = get_redis_client()
    # GETDEL делает ссылку одноразовой даже при двух параллельных запросах.
    user_id = await r.getdel(f"reset_pwd:{token}")

    if not user_id:
        return templates.TemplateResponse(request, "login.html", context={
            "error": "Срок действия ссылки истёк",
            "quote_text": get_random_quote()
        })

    # Обновляем пароль в PostgreSQL
    new_hash = generate_password_hash(new_password)
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET password_hash = %s WHERE id = %s", (new_hash, int(user_id)))
            conn.commit()

    return templates.TemplateResponse(request, "login.html", context={
        "success": "Тайный ключ успешно обновлен! Войдите с новым паролем.",
        "quote_text": get_random_quote()
    })
