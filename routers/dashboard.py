from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from dependencies import templates, get_current_user
from utils import load_chars  # 🆕 Добавили импорт функции

router = APIRouter(tags=["Dashboard"])


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(
        request: Request,
        current_user: dict = Depends(get_current_user)
):
    """
    Единая панель управления (Хаб).
    Доступна только авторизованным пользователям.
    """
    # 🆕 Загружаем персонажей текущего пользователя
    chars = load_chars(current_user['username'])

    return templates.TemplateResponse(
        request=request,
        name="MainMenu.html",
        context={
            "request": request,
            "username": current_user.get("username", "Путник"),
            "chars": chars  # 🆕 Передаём их в контекст шаблона
        }
    )