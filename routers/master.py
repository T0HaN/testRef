import json
import time
import asyncio
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request, Depends, Form, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, StreamingResponse
from psycopg2.extras import RealDictCursor

from models import RewardRequest, RollRequest
from dependencies import get_current_user, templates
import utils
from utils import (
    load_chars, save_chars,
    normalize_char, calculate_ac, prepare_skills_and_saves, get_class_features,
    calc_level_from_xp, calc_prof_bonus, get_level_progress, XP_THRESHOLDS,
    get_db_connection, get_redis_room_state, save_redis_room_state, get_random_quote, get_all_monsters,
    upload_image_to_s3, create_scene, get_room_scenes, set_active_scene, delete_scene
)
from sse import add_sse_listener, remove_sse_listener, broadcast_room_event
from routers.websockets import broadcast_ws_event

router = APIRouter(tags=["Master"])


def clean_text(text: str) -> str:
    """Убирает лишние переносы строк из hit_points и прочего"""
    if not isinstance(text, str):
        return text
    return " ".join(text.replace("\n", " ").split())


def cleanup_stale_players(room_id: str, timeout_seconds: int = 300):
    """
    Отключено: мы больше не удаляем игроков из таблицы room_players по таймауту.
    Статус онлайна теперь проверяется молниеносно через Redis.
    """
    pass


@router.get("/games", response_class=HTMLResponse)
async def games_dashboard(request: Request, current_user: dict = Depends(get_current_user)):
    """
    Единая панель кампаний.
    Загружает списки игр, где пользователь является Мастером и где он Игрок.
    """
    master_rooms = []
    player_rooms = []

    # 🆕 Загружаем персонажей текущего пользователя для модалки входа
    chars = load_chars(current_user['username'])

    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # 1. Загружаем кампании, где я — Мастер
                cur.execute("""
                    SELECT id, name, description, invite_code, max_players, active, created_at 
                    FROM rooms 
                    WHERE master_id = %s 
                    ORDER BY created_at DESC
                """, (current_user['id'],))
                master_rooms = cur.fetchall()

                # 2. Загружаем кампании, где я — Игрок (через связь many-to-many)
                cur.execute("""
                    SELECT r.id, r.name, r.description, r.active, rp.char_name, rp.character_id, rp.joined_at
                    FROM rooms r
                    JOIN room_players rp ON r.id = rp.room_id
                    WHERE rp.user_id = %s
                    ORDER BY rp.joined_at DESC
                """, (current_user['id'],))
                player_rooms = cur.fetchall()

    except Exception as e:
        print(f"❌ Ошибка БД при загрузке списка игр: {e}")
        import traceback
        traceback.print_exc()

    # Получаем случайную цитату для футера
    quote_text = get_random_quote()

    # Передаём данные в новый шаблон
    return templates.TemplateResponse(
        request=request,
        name="games.html",
        context={
            "master_rooms": master_rooms,
            "player_rooms": player_rooms,
            "username": current_user['username'],
            "quote_text": quote_text,
            "error": request.query_params.get("error"),
            "success": request.query_params.get("success"),
            "chars": chars
        }
    )


@router.post("/master/room/create")
async def create_room(
        request: Request,
        name: str = Form(...),
        description: Optional[str] = Form(""),
        max_players: int = Form(6),
        current_user: dict = Depends(get_current_user)
):
    name = name.strip()
    if not name:
        return RedirectResponse(url="/games?error=Название комнаты обязательно", status_code=303)

    invite_code = utils.generate_invite_code()
    max_p = max(1, min(max_players, 10))

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO rooms (master_id, name, description, invite_code, max_players, active)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (current_user['id'], name, description.strip(), invite_code, max_p, True))
                conn.commit()
    except Exception as e:
        print(f"❌ Ошибка создания комнаты в БД: {e}")
        return RedirectResponse(url="/games?error=Ошибка при создании комнаты", status_code=303)

    return RedirectResponse(url="/games?success=Комната успешно создана", status_code=303)


@router.post("/master/room/delete/{room_id}")
async def delete_room(room_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    try:
        room_id_int = int(room_id)
    except (ValueError, TypeError):
        return RedirectResponse(url="/games?error=Неверный ID комнаты", status_code=303)

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # Проверяем, принадлежит ли комната текущему пользователю
            cur.execute("SELECT id FROM rooms WHERE id = %s AND master_id = %s", (room_id_int, current_user['id']))
            if not cur.fetchone():
                return RedirectResponse(url="/games?error=Комната не найдена или нет прав", status_code=303)

            # Очищаем связи игроков и удаляем комнату
            cur.execute("DELETE FROM room_players WHERE room_id = %s", (room_id_int,))
            cur.execute("DELETE FROM rooms WHERE id = %s", (room_id_int,))
            conn.commit()

    return RedirectResponse(url="/games?success=Комната удалена", status_code=303)


@router.post("/master/room/toggle/{room_id}")
async def toggle_room_status(room_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    try:
        room_id_int = int(room_id)
    except (ValueError, TypeError):
        return RedirectResponse(url="/games", status_code=303)

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE rooms 
                SET active = NOT active 
                WHERE id = %s AND master_id = %s
            """, (room_id_int, current_user['id']))
            conn.commit()

    return RedirectResponse(url="/games", status_code=303)


@router.get("/master/room/{room_id}", response_class=HTMLResponse)
async def master_room(room_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    try:
        room_id_int = int(room_id)
    except (ValueError, TypeError):
        return RedirectResponse(url="/games?error=Неверный ID комнаты", status_code=303)

    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Проверяем права мастера через БД
            cur.execute("SELECT * FROM rooms WHERE id = %s AND master_id = %s", (room_id_int, current_user['id']))
            room = cur.fetchone()

            if not room:
                return RedirectResponse(url="/games?error=Доступ запрещен", status_code=303)

            # Достаем всех игроков из БД (теперь они не удаляются)
            cur.execute("""
                            SELECT rp.user_id, rp.character_id AS char_id, rp.char_name, u.username
                            FROM room_players rp
                            JOIN users u ON rp.user_id = u.id
                            WHERE rp.room_id = %s
                        """, (room_id_int,))
            current_players = cur.fetchall()

            # 🆕 НОВОЕ: Достаем каталог пропсов для комнаты
            cur.execute("SELECT * FROM props ORDER BY category, name")
            props = cur.fetchall()

    players_data = []
    for p in current_players:
        username = p['username']
        char_id_int = p['char_id']
        user_id = p['user_id']

        # Опрашиваем Redis: если ключ есть, значит игрок в сети
        is_online = False
        if utils.redis_client:
            redis_status = await utils.redis_client.get(f"user:{user_id}:online")
            is_online = bool(redis_status)

        user_chars = load_chars(username)
        char = next((c for c in user_chars if c['id'] == char_id_int), None)
        if char:
            char = normalize_char(char)
            lvl = char.get('level', 1)
            xp_prog = get_level_progress(char.get('xp', 0), lvl)
            next_xp = XP_THRESHOLDS[lvl] if lvl < 20 else "MAX"
            players_data.append({
                'username': username,
                'char': char,
                'xp_progress': xp_prog,
                'next_level_xp': next_xp,
                'is_online': is_online
            })

    # Извлечение данных из Redis
    ws_room = await get_redis_room_state(str(room_id_int))
    selected_monsters = ws_room.get('selected_monsters', [])

    # SSR: История чата
    chat_history = []
    if utils.redis_client:
        raw_history = await utils.redis_client.lrange(f"room:{room_id_int}:chat_log", -30, -1)
        for msg in raw_history:
            text_msg = msg if isinstance(msg, str) else msg.decode('utf-8')
            try:
                chat_history.append(json.loads(text_msg))
            except json.JSONDecodeError:
                pass

    return templates.TemplateResponse(request, "master_room.html", context={
        "room": room,
        "players": players_data,
        "selected_monsters": selected_monsters,
        "props": props,  # 🆕 НОВОЕ: Передаем пропсы в шаблон
        "username": current_user['username'],
        "chat_history": chat_history,
        "error": None,
        "success": None
    })


@router.get("/master/room/{room_id}/char/{char_id}", response_class=HTMLResponse)
async def master_view_character(
        request: Request,
        room_id: int,
        char_id: str,
        username: Optional[str] = None,
        current_user: dict = Depends(get_current_user)
):
    try:
        # Проверяем, что текущий пользователь — мастер этой комнаты
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM rooms WHERE id = %s AND master_id = %s", (room_id, current_user['id']))
                if not cur.fetchone():
                    return HTMLResponse("Доступ запрещен", status_code=403)

        if not username:
            return HTMLResponse("Ошибка: Не передан username в ссылке", status_code=400)

        user_chars = load_chars(username)
        char = next((c for c in user_chars if str(c.get('id')) == str(char_id)), None)

        if not char:
            return HTMLResponse(f"Персонаж не найден", status_code=404)

        char = normalize_char(char)
        char['features'] = get_class_features(
            char.get('char_class', ''),
            char.get('subclass', ''),
            char.get('level', 1)
        )

        saves, skills = [], []
        try:
            result = prepare_skills_and_saves(char)
            if isinstance(result, tuple) and len(result) == 2:
                saves, skills = result
        except Exception as e:
            print(f"❌ Ошибка в prepare_skills_and_saves: {e}")

        is_spellcaster = bool(char.get('spellcasting') and char['spellcasting'].get('level', 0) > 0)

        return templates.TemplateResponse(
            request=request,
            name="master_char_sheet.html",
            context={
                "request": request,
                "room_id": room_id,
                "char": char,
                "username": username,
                "saves": saves,
                "skills": skills,
                "is_spellcaster": is_spellcaster,
                "known_spells": char.get('spells', [])
            }
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return HTMLResponse(f"Ошибка сервера", status_code=500)


@router.get("/master/room/{room_id}/events")
async def master_room_events(room_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    """SSE endpoint для мастера"""
    try:
        room_id_int = int(room_id)
    except (ValueError, TypeError):
        return StreamingResponse(iter([]), status_code=404)

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM rooms WHERE id = %s AND master_id = %s", (room_id_int, current_user['id']))
            if not cur.fetchone():
                return StreamingResponse(iter([]), status_code=403)

    queue = add_sse_listener(str(room_id_int))

    async def event_stream():
        try:
            while True:
                if queue:
                    event = queue.pop(0)
                    yield f"event: {event['event']}\ndata: {json.dumps(event['data'], ensure_ascii=False)}\n\n"
                else:
                    await asyncio.sleep(0.5)
        finally:
            remove_sse_listener(str(room_id_int), queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.post("/room/{room_id}/roll/history")
async def save_roll_history(
        room_id: str,
        roll: RollRequest,
        request: Request,
        current_user: dict = Depends(get_current_user)
):
    try:
        room_id_int = int(room_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid room_id")

    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM rooms WHERE id = %s", (room_id_int,))
            room = cur.fetchone()
            if not room:
                raise HTTPException(status_code=404, detail="Room not found")

            is_master = (room['master_id'] == current_user['id'])

            cur.execute("SELECT 1 FROM room_players WHERE room_id = %s AND user_id = %s",
                        (room_id_int, current_user['id']))
            is_player = cur.fetchone() is not None

    if not (is_master or is_player):
        raise HTTPException(status_code=403, detail="Access denied")

    roll_entry = {
        'id': f"roll_{int(time.time() * 1000)}",
        'timestamp': time.time(),
        'player': current_user['username'],
        **roll.dict()
    }

    # Сохраняем в Redis историю бросков
    if utils.redis_client:
        await utils.redis_client.lpush(f"room:{room_id_int}:rolls", json.dumps(roll_entry))
        await utils.redis_client.ltrim(f"room:{room_id_int}:rolls", 0, 99)

    broadcast_room_event(str(room_id_int), 'roll_added', roll_entry)
    return {'status': 'ok', 'roll': roll_entry}


@router.get("/master/room/{room_id}/rewards", response_class=HTMLResponse)
async def master_rewards_page(room_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    """Отдельная страница наград"""
    try:
        room_id_int = int(room_id)
    except (ValueError, TypeError):
        return RedirectResponse(url="/games", status_code=303)

    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM rooms WHERE id = %s AND master_id = %s", (room_id_int, current_user['id']))
            room = cur.fetchone()
            if not room:
                return RedirectResponse(url="/games", status_code=303)

            cur.execute("""
                            SELECT rp.user_id, rp.character_id AS char_id, rp.char_name, u.username
                            FROM room_players rp
                            JOIN users u ON rp.user_id = u.id
                            WHERE rp.room_id = %s
                        """, (room_id_int,))
            current_players = cur.fetchall()

    players_data = []
    for p in current_players:
        username = p['username']
        char_id_int = p['char_id']
        user_chars = load_chars(username)
        char = next((c for c in user_chars if c['id'] == char_id_int), None)
        if char:
            players_data.append({
                'username': username,
                'char': normalize_char(char)
            })

    return templates.TemplateResponse(request, "master_rewards.html", context={
        "room": room,
        "players": players_data,
        "username": current_user['username'],
        "error": None,
        "success": None
    })


@router.post("/master/room/{room_id}/reward")
async def master_reward(
        room_id: str,
        reward: RewardRequest,
        current_user: dict = Depends(get_current_user)
):
    """Выдача наград"""
    try:
        room_id_int = int(room_id)
    except (ValueError, TypeError):
        return {"status": "error", "error": "Неверный ID комнаты"}

    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM rooms WHERE id = %s AND master_id = %s", (room_id_int, current_user['id']))
            room = cur.fetchone()
            if not room:
                return {"status": "error", "error": "Комната не найдена"}

            cur.execute("""
                            SELECT rp.user_id, rp.character_id AS char_id, rp.char_name, u.username
                            FROM room_players rp
                            JOIN users u ON rp.user_id = u.id
                            WHERE rp.room_id = %s
                        """, (room_id_int,))
            current_players = cur.fetchall()

    targets = []
    if str(reward.target).strip().lower() == 'all':
        for p in current_players:
            targets.append({
                'username': p['username'],
                'char_id': p['char_id'],
                'char_name': p['char_name']
            })
    else:
        try:
            target_char_id = int(reward.target)
            for p in current_players:
                if int(p['char_id']) == target_char_id:
                    targets.append({
                        'username': p['username'],
                        'char_id': target_char_id,
                        'char_name': p['char_name']
                    })
                    break
        except (ValueError, TypeError):
            return {"status": "error", "error": "Неверный ID персонажа"}

    if not targets:
        return {"status": "error", "error": "Нет игроков для награды"}

    rewarded_count = 0
    for t in targets:
        username = t['username']
        char_id = t['char_id']

        user_chars = load_chars(username)
        char = next((c for c in user_chars if c.get('id') == int(char_id)), None)
        if not char:
            continue

        if reward.xp > 0:
            old_xp = char.get('xp', 0)
            char['xp'] = old_xp + reward.xp
            new_level = calc_level_from_xp(char['xp'])
            char['level'] = new_level
            char.setdefault('attributes', {})
            char['attributes']['prof_bonus'] = f"+{calc_prof_bonus(new_level)}"

        if reward.coins:
            char.setdefault('inventory', {})
            char['inventory'].setdefault('coins', {'cp': 0, 'sp': 0, 'ep': 0, 'gp': 0, 'pp': 0})
            for coin_type, amount in reward.coins.items():
                if amount and amount > 0 and coin_type in char['inventory']['coins']:
                    char['inventory']['coins'][coin_type] += amount

        save_chars(username, user_chars)
        rewarded_count += 1

    return {
        "status": "ok",
        "message": f"Награда выдана {rewarded_count} игрокам",
        "rewarded_count": rewarded_count
    }


@router.get("/master/prep/{room_id}")
async def master_prep(room_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    try:
        room_id_int = int(room_id)
    except (ValueError, TypeError):
        return RedirectResponse(url="/games", status_code=303)

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM rooms WHERE id = %s AND master_id = %s", (room_id_int, current_user['id']))
            if not cur.fetchone():
                return RedirectResponse(url="/games", status_code=303)

    monsters = get_all_monsters()
    quote_text = get_random_quote()

    return templates.TemplateResponse(request, "master_prep.html", context={
        "monsters": monsters,
        "room_id": room_id,
        "quote_text": quote_text
    })


@router.post("/master/prep/{room_id}/save")
async def save_monster_prep(room_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    try:
        room_id_int = int(room_id)
        room_id_str = str(room_id_int)
    except (ValueError, TypeError):
        return JSONResponse(status_code=400, content={"error": "Invalid room_id"})

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM rooms WHERE id = %s AND master_id = %s", (room_id_int, current_user['id']))
            if not cur.fetchone():
                return JSONResponse(status_code=403, content={"error": "Access denied"})

    try:
        content_type = request.headers.get('content-type', '')
        if 'multipart/form-data' in content_type or 'application/x-www-form-urlencoded' in content_type:
            form = await request.form()
            monsters_json = form.get("monsters_data")
        else:
            data = await request.json()
            monsters_json = data.get("monsters_data")

        selected_monsters = json.loads(monsters_json) if monsters_json else []

        room = await get_redis_room_state(room_id_str)
        room['selected_monsters'] = selected_monsters
        await save_redis_room_state(room_id_str, room)

        return RedirectResponse(url=f"/master/room/{room_id}", status_code=303)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/api/room/{room_id}/scene/upload")
async def api_upload_scene(
        room_id: int,
        name: str = Form(...),
        width: int = Form(1920),
        height: int = Form(1080),
        file: UploadFile = File(...),
        current_user: dict = Depends(get_current_user)
):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM rooms WHERE id = %s AND master_id = %s", (room_id, current_user['id']))
            if not cur.fetchone():
                return JSONResponse(status_code=403, content={"status": "error", "message": "Access denied"})

    try:
        background_url = await upload_image_to_s3(file, prefix=f"room_{room_id}")
        scene = create_scene(room_id, name, background_url, width, height)

        if 'created_at' in scene and scene['created_at']:
            scene['created_at'] = scene['created_at'].isoformat()

        if scene.get('is_active'):
            room_state = await get_redis_room_state(str(room_id))
            room_state['map_image'] = scene['background_url']
            room_state['map_width'] = scene['map_width']
            room_state['map_height'] = scene['map_height']
            await save_redis_room_state(str(room_id), room_state)

            await broadcast_ws_event(str(room_id), {
                'type': 'map_update',
                'image': scene['background_url'],
                'width': scene['map_width'],
                'height': scene['map_height'],
                'scene_id': scene['id']
            })

        return JSONResponse(content={"status": "ok", "scene": scene})
    except Exception as e:
        return JSONResponse(content={"status": "error", "message": str(e)}, status_code=500)


@router.get("/api/room/{room_id}/scenes")
async def api_get_scenes(room_id: int, current_user: dict = Depends(get_current_user)):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM rooms WHERE id = %s AND master_id = %s", (room_id, current_user['id']))
            if not cur.fetchone():
                return JSONResponse(status_code=403, content={"status": "error", "message": "Access denied"})

    scenes = get_room_scenes(room_id)
    for s in scenes:
        if 'created_at' in s and s['created_at']:
            s['created_at'] = s['created_at'].isoformat()
    return JSONResponse(content={"status": "ok", "scenes": scenes})


@router.post("/api/room/{room_id}/scene/{scene_id}/activate")
async def api_activate_scene(room_id: int, scene_id: int, current_user: dict = Depends(get_current_user)):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM rooms WHERE id = %s AND master_id = %s", (room_id, current_user['id']))
            if not cur.fetchone():
                return JSONResponse(status_code=403, content={"status": "error", "message": "Access denied"})

    set_active_scene(room_id, scene_id)

    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM scenes WHERE id = %s", (scene_id,))
            scene = cur.fetchone()

    if scene:
        room_state = await get_redis_room_state(str(room_id))
        room_state['map_image'] = scene['background_url']
        room_state['map_width'] = scene['map_width']
        room_state['map_height'] = scene['map_height']
        await save_redis_room_state(str(room_id), room_state)

        await broadcast_ws_event(str(room_id), {
            'type': 'map_update',
            'image': scene['background_url'],
            'width': scene['map_width'],
            'height': scene['map_height'],
            'scene_id': scene['id']
        })

    return JSONResponse(content={"status": "ok"})


@router.delete("/api/room/{room_id}/scene/{scene_id}")
async def api_delete_scene(room_id: int, scene_id: int, current_user: dict = Depends(get_current_user)):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM rooms WHERE id = %s AND master_id = %s", (room_id, current_user['id']))
            if not cur.fetchone():
                return JSONResponse(status_code=403, content={"status": "error", "message": "Access denied"})

    scene = utils.delete_scene(room_id, scene_id)
    if not scene:
        return JSONResponse(status_code=404, content={"status": "error", "message": "Сцена не найдена"})

    if scene.get('is_active'):
        room_state = await get_redis_room_state(str(room_id))
        room_state['map_image'] = None
        room_state['map_width'] = 0
        room_state['map_height'] = 0
        await save_redis_room_state(str(room_id), room_state)

        await broadcast_ws_event(str(room_id), {'type': 'map_clear'})

    return JSONResponse(content={"status": "ok"})


@router.get("/media/{path:path}")
async def get_media_from_s3(path: str):
    """Проксируем картинки из внутреннего MinIO наружу"""
    try:
        response = utils.s3_client.get_object(Bucket=utils.settings.S3_BUCKET, Key=path)

        def iterfile():
            for chunk in response['Body'].iter_chunks(chunk_size=1024 * 1024):
                yield chunk

        return StreamingResponse(iterfile(), media_type=response['ContentType'])
    except Exception as e:
        print(f"Ошибка получения файла из S3: {e}")
        raise HTTPException(status_code=404, detail="Image not found")


# 🆕 НОВОЕ: Эндпоинт для загрузки новых пропсов в MinIO и базу данных
# 🆕 ИСПРАВЛЕНО: Эндпоинт для загрузки новых пропсов в MinIO и базу данных
@router.post("/api/props/upload")
async def api_upload_prop(
        name: str = Form(...),
        category: str = Form("Разное"),
        default_size: int = Form(50),
        file: UploadFile = File(...),
        current_user: dict = Depends(get_current_user)
):
    try:
        # 1. Загружаем картинку в S3
        image_url = await upload_image_to_s3(file, prefix="props")

        # 2. Сохраняем в таблицу
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    INSERT INTO props (name, category, image_url, default_size)
                    VALUES (%s, %s, %s, %s) RETURNING *
                """, (name, category, image_url, default_size))
                new_prop = cur.fetchone()
                conn.commit()

        # Конвертируем datetime в строку, чтобы JSONResponse не ругался
        if new_prop and 'created_at' in new_prop and new_prop['created_at']:
            new_prop['created_at'] = new_prop['created_at'].isoformat()

        return JSONResponse(content={"status": "ok", "prop": new_prop})
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

# === Монстры ===

@router.get("/monsters/new")
async def new_monster_form(request: Request, room_id: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    """Страница добавления нового монстра."""
    return templates.TemplateResponse(request, "add_monster.html", {"request": request, "room_id": room_id})


def _parse_list_field(value: str) -> list:
    """Разбирает текстовое поле списка: принимает JSON-массив или список по строкам."""
    if not value or not value.strip():
        return []
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return parsed
    except Exception:
        pass
    return [line.strip() for line in value.splitlines() if line.strip()]


@router.post("/monsters/new")
async def create_monster(
    request: Request,
    name: str = Form(...),
    meta: str = Form(""),
    armor_class: int = Form(...),
    hit_points: int = Form(...),
    hit_dice: str = Form(...),
    speed: str = Form(...),
    challenge_rating: str = Form(...),
    traits: str = Form(""),
    actions: str = Form(""),
    legendary_actions: str = Form(""),
    attr_str: int = Form(10),
    attr_dex: int = Form(10),
    attr_con: int = Form(10),
    attr_int: int = Form(10),
    attr_wis: int = Form(10),
    attr_cha: int = Form(10),
    token_image: UploadFile = File(...),
    room_id: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user)
):
    """Обработка формы добавления монстра."""
    try:
        # 1. Загружаем изображение в S3 (MinIO)
        token_path = await upload_image_to_s3(token_image, prefix="monsters")

        # 2. Собираем атрибуты и списки из простых полей формы
        attrs = {"STR": attr_str, "DEX": attr_dex, "CON": attr_con,
                 "INT": attr_int, "WIS": attr_wis, "CHA": attr_cha}
        traits_list = _parse_list_field(traits)
        actions_list = _parse_list_field(actions)
        leg_actions_list = _parse_list_field(legendary_actions)

        # 3. Сохраняем в БД
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    INSERT INTO monsters (name, meta, armor_class, hit_points, hit_dice, speed, attributes, challenge_rating, traits, actions, legendary_actions, token_path)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (name, meta, armor_class, hit_points, hit_dice, speed, json.dumps(attrs), challenge_rating, json.dumps(traits_list), json.dumps(actions_list), json.dumps(leg_actions_list), token_path))
                new_id = cur.fetchone()['id']
                conn.commit()

        # 4. Редирект
        if room_id:
            return RedirectResponse(url=f"/master/prep/{room_id}", status_code=303)
        else:
            return RedirectResponse(url="/games", status_code=303)

    except Exception as e:
        print(f"❌ Ошибка при создании монстра: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
