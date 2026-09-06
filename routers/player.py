import asyncio
import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Request, Depends, HTTPException, Query, Form
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse, JSONResponse
from psycopg2.extras import RealDictCursor

from models import AmmoUseRequest, SpellCreate
from dependencies import get_current_user, templates
import utils
from utils import (
    load_chars, save_chars, normalize_char, prepare_skills_and_saves,
    get_spells_for_class, get_db_connection
)
from sse import add_sse_listener, remove_sse_listener, broadcast_room_event
import psycopg2
router = APIRouter(tags=["Player"])


# УДАЛЕНО: /player/join (GET и POST) и /player/join/{room_id}
# Причина: Вход в игру теперь происходит через единый роут /room/join из модального окна на странице /chars


@router.get("/player/room/{room_id}", response_class=HTMLResponse)
async def player_room(
        room_id: str,
        request: Request,
        current_user: dict = Depends(get_current_user)
):
    """Страница виртуального стола для игрока"""
    try:
        room_id_int = int(room_id)
    except (ValueError, TypeError):
        return RedirectResponse(url="/games?error=Неверный ID комнаты", status_code=303)

    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # 1. Проверяем, существует ли комната
            cur.execute("SELECT * FROM rooms WHERE id = %s", (room_id_int,))
            room = cur.fetchone()

            if not room:
                return RedirectResponse(url="/games?error=Комната не найдена", status_code=303)

            # 2. Проверяем, есть ли текущий пользователь в списке игроков этой комнаты
            cur.execute("""
                            SELECT character_id AS char_id, char_name 
                            FROM room_players 
                            WHERE room_id = %s AND user_id = %s
                        """, (room_id_int, current_user['id']))
            player_entry = cur.fetchone()

    if not player_entry:
        return RedirectResponse(url="/games?error=Вы не присоединились к этой игре", status_code=303)


    chars = load_chars(current_user['username'])
    try:
        player_char_id_int = int(player_entry['char_id'])
    except (ValueError, TypeError):
        return RedirectResponse(url="/games?error=Неверный ID персонажа", status_code=303)

    char = next((c for c in chars if c['id'] == player_char_id_int), None)

    if not char:
        return RedirectResponse(url="/games?error=Персонаж не найден", status_code=303)

    # 4. Подготавливаем данные для отображения листа на столе
    char = normalize_char(char)
    saves, skills = prepare_skills_and_saves(char)

    char_class = char.get('char_class', '')
    is_spellcaster = char_class in ['Волшебник', 'Жрец', 'Бард', 'Колдун', 'Чародей', 'Друид', 'Паладин', 'Следопыт',
                                    'Изобретатель']

    known_spells = []
    if is_spellcaster:
        known_spells_names = char.get('inventory', {}).get('known_spells', [])
        _, known_spells, _ = get_spells_for_class(char_class, char.get('level', 1), known_spells_names)

    # 5. SSR: Вытягиваем историю чата из Redis
    chat_history = []
    if utils.redis_client:
        raw_history = await utils.redis_client.lrange(f"room:{room_id_int}:chat_log", -30, -1)
        for msg in raw_history:
            text_msg = msg if isinstance(msg, str) else msg.decode('utf-8')
            try:
                chat_history.append(json.loads(text_msg))
            except json.JSONDecodeError:
                pass

    return templates.TemplateResponse(request, "player_room.html", context={
        "room": room,
        "char": char,
        "saves": saves,
        "skills": skills,
        "is_spellcaster": is_spellcaster,
        "known_spells": known_spells,
        "username": current_user['username'],
        "chat_history": chat_history,
        "error": None,
        "success": None
    })


@router.get("/api/room/{room_id}/chat/history")
async def get_chat_history(
        room_id: str,
        offset: int = Query(0, description="Сколько сообщений уже загружено"),
        limit: int = Query(20, description="Сколько старых сообщений отдать")
):
    """API-эндпоинт для ленивой загрузки старых сообщений чата (Lazy Loading)"""
    if not utils.redis_client:
        return JSONResponse({"messages": []})

    try:
        room_id_int = int(room_id)
    except ValueError:
        return JSONResponse({"messages": []})

    end_idx = -1 - offset
    start_idx = end_idx - limit + 1

    raw_history = await utils.redis_client.lrange(f"room:{room_id_int}:chat_log", start_idx, end_idx)

    messages = []
    for msg in raw_history:
        text_msg = msg if isinstance(msg, str) else msg.decode('utf-8')
        try:
            messages.append(json.loads(text_msg))
        except json.JSONDecodeError:
            pass

    return JSONResponse({"messages": messages})


@router.get("/player/room/{room_id}/events")
async def player_room_events(room_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    """SSE для игроков (броски)"""
    try:
        room_id_int = int(room_id)
    except (ValueError, TypeError):
        return StreamingResponse(iter([]), status_code=404)

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # Проверяем доступ к комнате
            cur.execute("SELECT id FROM room_players WHERE room_id = %s AND user_id = %s",
                        (room_id_int, current_user['id']))
            if not cur.fetchone():
                return StreamingResponse(iter([]), status_code=403)

    queue = add_sse_listener(str(room_id_int))

    async def event_stream():
        try:
            while True:
                if queue:
                    event = queue.pop(0)
                    if event['event'] == 'roll_added':
                        yield f"event: {event['event']}\ndata: {json.dumps(event['data'], ensure_ascii=False)}\n\n"
                else:
                    await asyncio.sleep(0.5)
        finally:
            remove_sse_listener(str(room_id_int), queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"}
    )


@router.post("/player/room/{room_id}/ammo/use")
async def use_ammo(
        room_id: str,
        ammo: AmmoUseRequest,
        current_user: dict = Depends(get_current_user)
):
    """Трата боеприпасов (стрел/болтов) из инвентаря игрока"""
    try:
        room_id_int = int(room_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid room_id")

    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT char_id FROM room_players WHERE room_id = %s AND user_id = %s",
                        (room_id_int, current_user['id']))
            player_entry = cur.fetchone()

    if not player_entry:
        raise HTTPException(status_code=404, detail="Player not found in this room")

    user_chars = load_chars(current_user['username'])
    try:
        player_char_id_int = int(player_entry['char_id'])
    except (ValueError, TypeError):
        raise HTTPException(status_code=404, detail="Invalid char_id")

    char = next((c for c in user_chars if c['id'] == player_char_id_int), None)
    if not char:
        raise HTTPException(status_code=404, detail="Character not found")

    char = normalize_char(char)
    ammo_list = char['inventory'].get(ammo.ammo_type, [])
    remaining = ammo.qty

    for item in ammo_list:
        if remaining <= 0:
            break
        if item.get('qty', 0) > 0:
            use_amount = min(remaining, item['qty'])
            item['qty'] -= use_amount
            remaining -= use_amount

    save_chars(current_user['username'], user_chars)
    return {'status': 'ok', 'remaining': char['inventory'].get(ammo.ammo_type, [])}


@router.get("/player/room/{room_id}/leave")
async def leave_room(
        room_id: str,
        request: Request,
        current_user: dict = Depends(get_current_user)
):
    """Выход игрока из комнаты навсегда"""
    try:
        room_id_int = int(room_id)
    except (ValueError, TypeError):
        return RedirectResponse(url="/games", status_code=303)

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # Удаляем запись игрока из комнаты
            cur.execute("DELETE FROM room_players WHERE room_id = %s AND user_id = %s",
                        (room_id_int, current_user['id']))
            conn.commit()

    # Оповещаем вебсокеты, что игрок ушел
    broadcast_room_event(str(room_id_int), 'player_left', {'username': current_user['username']})

    # Возвращаем в список игр
    return RedirectResponse(url="/games", status_code=303)


# 🆕 ПОЛНОСТЬЮ ОБНОВЛЕННЫЙ ЭНДПОИНТ (Redis вместо PostgreSQL)
@router.post("/player/heartbeat")
async def player_heartbeat(current_user: dict = Depends(get_current_user)):
    """Обновляет статус онлайна игрока в Redis"""
    if utils.redis_client:
        # Устанавливаем ключ, который сам исчезнет через 300 секунд (5 минут)
        # Если игрок шлет пульс, таймер обновляется. Закроет вкладку — ключ умрет.
        await utils.redis_client.setex(f"user:{current_user['id']}:online", 300, "1")

    return {'status': 'ok'}


@router.post("/api/spells")
def create_spell(spell: SpellCreate):
    """Добавляет новое заклинание в общую таблицу (подключение через .env)."""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                        INSERT INTO spells (
                            name_ru, name_en, level, school, casting_time,
                            range, components, duration, description, source, classes
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (spell.name_ru, spell.name_en, spell.level, spell.school, spell.casting_time,
                     spell.range, spell.components, spell.duration, spell.description, spell.source,
                     spell.classes)
                )
                conn.commit()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка базы данных: {str(e)}")

    return {"status": "success", "message": f"Заклинание «{spell.name_ru}» успешно добавлено!"}


@router.get("/editspells", response_class=HTMLResponse)
async def render_edit_spells_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="editspells.html",
        context={
            # сюда можешь передать любые другие переменные для шаблона, если нужны
        }
    )


@router.post("/room/join")
async def join_room(
        request: Request,
        invite_code: str = Form(...),
        char_id: int = Form(None),  # Опционально, на случай если Мастер случайно введет код
        current_user: dict = Depends(get_current_user)
):
    """Обработчик входа в комнату по коду приглашения"""
    invite_code = invite_code.strip()

    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # 1. Ищем комнату по коду
            cur.execute("SELECT * FROM rooms WHERE invite_code = %s", (invite_code,))
            room = cur.fetchone()

            if not room:
                return RedirectResponse(url="/games?error=Неверный код приглашения", status_code=303)

            room_id = room['id']

            # 2. Если код ввёл Мастер этой же комнаты — просто пускаем его за стол
            if room['master_id'] == current_user['id']:
                return RedirectResponse(url=f"/master/room/{room_id}", status_code=303)

            # 3. Защита для игроков: обязательно нужен персонаж
            if not char_id:
                return RedirectResponse(url="/games?error=Необходимо выбрать персонажа для игры", status_code=303)

            # 4. Проверяем, не присоединился ли игрок ранее
            cur.execute("SELECT * FROM room_players WHERE room_id = %s AND user_id = %s", (room_id, current_user['id']))
            if cur.fetchone():
                return RedirectResponse(url=f"/player/room/{room_id}", status_code=303)

            # 5. Проверяем существование выбранного персонажа
            from utils import load_chars
            chars = load_chars(current_user['username'])
            char = next((c for c in chars if c['id'] == char_id), None)

            if not char:
                return RedirectResponse(url="/games?error=Выбранный персонаж не найден", status_code=303)

            char_name = char.get('name', 'Безымянный')

            # 6. Проверяем лимит игроков в комнате
            cur.execute("SELECT COUNT(*) as cnt FROM room_players WHERE room_id = %s", (room_id,))
            current_players_count = cur.fetchone()['cnt']
            if current_players_count >= room['max_players']:
                return RedirectResponse(url="/games?error=Комната уже заполнена", status_code=303)

            # 7. Сажаем игрока за стол
            cur.execute("""
                INSERT INTO room_players (room_id, user_id, character_id, char_name) 
                VALUES (%s, %s, %s, %s)
            """, (room_id, current_user['id'], char_id, char_name))
            conn.commit()

    return RedirectResponse(url=f"/player/room/{room_id}", status_code=303)