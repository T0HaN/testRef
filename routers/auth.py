import time
import json
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from werkzeug.security import generate_password_hash, check_password_hash
import psycopg2.extras

# Подключаем работу с БД вместо старых JSON-утилит
from utils import get_random_quote, get_db_connection
from dependencies import templates, sign_session_data, unsign_session_data

router = APIRouter(tags=["Auth"])


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

    if action == 'register':
        if not email:
            return templates.TemplateResponse(request, "login.html", context={
                "error": "Для регистрации необходима электронная почта",
                "quote_text": get_random_quote()
            })

        email = email.strip().lower()

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

        except Exception as e:
            print(f"Ошибка БД при регистрации: {e}")
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

            if not user_data or not check_password_hash(user_data['password_hash'], password):
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
                samesite="lax"
            )
            return response

        except Exception as e:
            print(f"Ошибка БД при логине: {e}")
            return templates.TemplateResponse(request, "login.html", context={
                "error": "Внутренняя ошибка сервера при авторизации",
                "quote_text": get_random_quote()
            })


@router.get("/logout")
async def logout():
    """Выход из системы и очистка сессии."""
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("session")
    return response