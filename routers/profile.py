import json
import secrets
from fastapi import APIRouter, Request, Form, Depends, BackgroundTasks, status
from fastapi.responses import HTMLResponse, RedirectResponse
from werkzeug.security import generate_password_hash, check_password_hash
import psycopg2.extras

from config import settings
from dependencies import templates, get_current_user
from utils import get_db_connection, get_redis_client, send_email_sync

profile_router = APIRouter(prefix="/profile", tags=["Profile"])


def get_user_db_record(user_id: int) -> dict:
    """Извлекает свежие данные пользователя из базы данных."""
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT id, username, email, password_hash FROM users WHERE id = %s", (user_id,))
            return cur.fetchone()


# --- СТРАНИЦА ПРОФИЛЯ ---
@profile_router.get("", response_class=HTMLResponse)
async def view_profile(
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    user = get_user_db_record(current_user['id'])
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse(request, "profile.html", context={
        "user": user,
        "success": request.query_params.get("success"),
        "error": request.query_params.get("error"),
        "info": request.query_params.get("info")
    })


# --- СМЕНА ТАЙНОГО КЛЮЧА (ПАРОЛЯ) ---
@profile_router.post("/change-password")
async def change_password(
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    current_user: dict = Depends(get_current_user)
):
    user = get_user_db_record(current_user['id'])
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    if not check_password_hash(user['password_hash'], current_password):
        return RedirectResponse(url="/profile?error=Текущий+пароль+указан+неверно", status_code=status.HTTP_303_SEE_OTHER)

    if new_password != confirm_password:
        return RedirectResponse(url="/profile?error=Новые+пароли+не+совпадают", status_code=status.HTTP_303_SEE_OTHER)

    if len(new_password) < 4:
        return RedirectResponse(url="/profile?error=Пароль+должен+быть+не+менее+4+символов", status_code=status.HTTP_303_SEE_OTHER)

    new_hash = generate_password_hash(new_password)
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET password_hash = %s WHERE id = %s", (new_hash, user['id']))
            conn.commit()

    return RedirectResponse(url="/profile?success=Тайный+ключ+успешно+обновлён", status_code=status.HTTP_303_SEE_OTHER)


# --- ЗАПРОС НА СМЕНУ EMAIL ---
@profile_router.post("/change-email")
async def request_email_change(
    background_tasks: BackgroundTasks,
    new_email: str = Form(...),
    current_user: dict = Depends(get_current_user)
):
    user = get_user_db_record(current_user['id'])
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    new_email = new_email.strip().lower()

    if new_email == (user.get('email') or '').lower():
        return RedirectResponse(url="/profile?error=Вы+указали+свой+текущий+адрес", status_code=status.HTTP_303_SEE_OTHER)

    # Проверяем, не занят ли email другим аккаунтом
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE email = %s AND id != %s", (new_email, user['id']))
            if cur.fetchone():
                return RedirectResponse(url="/profile?error=Этот+адрес+уже+занят+другим+путником", status_code=status.HTTP_303_SEE_OTHER)

    # Генерируем токен и кладём в Redis на 1 час
    token = secrets.token_urlsafe(32)
    payload = json.dumps({"user_id": user['id'], "new_email": new_email})
    
    r = get_redis_client()
    r.setex(f"email_change:{token}", 3600, payload)

    confirm_link = f"{settings.APP_BASE_URL}/profile/confirm-email?token={token}"

    email_body = f"""
    <div style="background-color: #141418; color: #e0d4b8; padding: 25px; font-family: Georgia, serif; border: 1px solid #3a352a; border-radius: 8px; max-width: 500px;">
        <h2 style="color: #c9a961; text-transform: uppercase; letter-spacing: 0.1em; margin-top: 0;">Смена свитка связи</h2>
        <p>Приветствуем, <strong>{user['username']}</strong>!</p>
        <p style="color: #a89f8a;">Вы запросили привязку этого почтового адреса к вашей летописи в Folio.</p>
        <div style="margin: 25px 0; text-align: center;">
            <a href="{confirm_link}" style="background: linear-gradient(145deg, #c9a961, #8b7542); color: #0a0a0c; padding: 12px 20px; text-decoration: none; font-weight: bold; border-radius: 6px; display: inline-block;">
                🕊️ Подтвердить новый адрес
            </a>
        </div>
        <p style="font-size: 0.85rem; color: #8b7542;">Ссылка действует 1 час. Если вы не делали этот запрос, проигнорируйте письмо.</p>
    </div>
    """

    background_tasks.add_task(
        send_email_sync,
        to_email=new_email,
        subject="Подтверждение новой почты в Folio",
        html_content=email_body
    )

    return RedirectResponse(
        url="/profile?info=Свиток+подтверждения+отправлен+на+новый+адрес",
        status_code=status.HTTP_303_SEE_OTHER
    )


# --- ПОДТВЕРЖДЕНИЕ НОВОГО EMAIL ПО ТОКЕНУ ---
@profile_router.get("/confirm-email")
async def confirm_email_change(
    token: str,
    current_user: dict = Depends(get_current_user)
):
    r = get_redis_client()
    data_raw = r.get(f"email_change:{token}")

    if not data_raw:
        return RedirectResponse(
            url="/profile?error=Ссылка+подтверждения+устарела+или+недействительна",
            status_code=status.HTTP_303_SEE_OTHER
        )

    data = json.loads(data_raw)

    # Проверяем, что подтверждает именно тот пользователь, который запросил смену
    if data['user_id'] != current_user['id']:
        return RedirectResponse(
            url="/profile?error=Ошибка+доступа+к+операции",
            status_code=status.HTTP_303_SEE_OTHER
        )

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET email = %s WHERE id = %s", (data['new_email'], data['user_id']))
            conn.commit()

    # Одноразовый токен
    r.delete(f"email_change:{token}")

    return RedirectResponse(
        url="/profile?success=Почтовый+адрес+успешно+обновлён",
        status_code=status.HTTP_303_SEE_OTHER
    )