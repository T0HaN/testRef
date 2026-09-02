import asyncio
import json
import time
import uuid
from urllib.parse import urlsplit

from config import settings

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from utils import (load_rooms, save_rooms, get_redis_room_state, save_redis_room_state,
                       load_chars)
import utils  # Для доступа к глобальному redis_client
from dependencies import unsign_session_data
from pydantic import ValidationError

from ws_schemas import InitSchema, WS_SCHEMAS

router = APIRouter(tags=["WebSockets"])

# Глобальный словарь для отслеживания количества активных вкладок у игрока
player_connections = {}


def _is_origin_allowed(websocket: WebSocket) -> bool:
    """CSWSH: разрешаем Origin, совпадающий с Host, или из списка WS_ALLOWED_ORIGINS."""
    origin = websocket.headers.get("origin")
    if not origin:
        # Не-браузерный клиент без Origin — полагаемся на подписанную cookie.
        return True
    try:
        origin_netloc = urlsplit(origin).netloc.lower()
    except ValueError:
        return False
    if not origin_netloc:
        return False

    host = (websocket.headers.get("host") or "").lower()
    if origin_netloc == host:
        return True

    allowed = [o.strip().lower() for o in settings.WS_ALLOWED_ORIGINS.split(",") if o.strip()]
    return origin_netloc in allowed



async def broadcast_ws_event(room_id: str, message: dict):
    """
    Универсальная функция трансляции событий.
    Публикует сообщение в Redis-канал, откуда его подхватят все воркеры.
    """
    if utils.redis_client:
        await utils.redis_client.publish(f"room:{room_id}:channel", json.dumps(message))


@router.websocket("/ws/room/{room_id}")
async def room_websocket(websocket: WebSocket, room_id: str):
    # 🛡️ 0. CSWSH: проверяем Origin до рукопожатия
    if not _is_origin_allowed(websocket):
        await websocket.close(code=4403, reason="Origin not allowed")
        return

    await websocket.accept()

    # 🛡️ 1. Безопасное извлечение и валидация пользователя из Cookie
    session_cookie = websocket.cookies.get("session")
    if not session_cookie:
        await websocket.close(code=4001, reason="No session cookie")
        return

    user_data = unsign_session_data(session_cookie)
    if not user_data or not isinstance(user_data, dict):
        await websocket.close(code=4001, reason="Invalid session signature")
        return

    username = user_data.get('username')
    user_role = user_data.get('role', 'player')

    # ✅ 2. Проверка существования комнаты
    try:
        room_id_int = int(room_id)
        room_id_str = str(room_id_int)
    except (ValueError, TypeError):
        await websocket.close(code=4004, reason="Invalid room_id")
        return

    rooms_data = load_rooms()
    room_data = next((r for r in rooms_data['rooms'] if r['id'] == room_id_int), None)
    if not room_data:
        await websocket.close(code=4004, reason="Room not found")
        return

    is_master = (room_data.get('master_id') == username) or (
            user_role == 'master' and room_data.get('master_id') == username)

    # 🛡️ Идентификаторы персонажей, которыми владеет пользователь (нужно для прав на токены)
    owned_char_ids = set()
    if not is_master and username:
        try:
            owned_char_ids = {str(c.get('id')) for c in load_chars(username)}
        except Exception as e:
            print(f"⚠️ Не удалось загрузить персонажей игрока {username}: {e}")
            owned_char_ids = set()

    try:
        init_data = await asyncio.wait_for(websocket.receive_json(), timeout=5.0)
        # Валидация первого сообщения (char_name / username)
        init_data = InitSchema(**init_data).model_dump()
        char_name = init_data.get('char_name') or username
    except Exception:
        char_name = username

    # 🆕 Увеличиваем счетчик подключений этого игрока
    conn_key = f"{room_id_str}_{username}"
    player_connections[conn_key] = player_connections.get(conn_key, 0) + 1

    # 📦 3. Инициализация стола из Redis
    state = await get_redis_room_state(room_id_str)

    await websocket.send_json({
        'type': 'init',
        'is_master': is_master,
        'username': username,
        'char_name': char_name
    })

    if state.get('map_image'):
        await websocket.send_json({
            'type': 'map_update',
            'image': state['map_image'],
            'width': state.get('map_width', 0),
            'height': state.get('map_height', 0),
            'is_master': is_master
        })

    # Отправляем сохраненный размер сетки при загрузке страницы
    if state.get('grid_size'):
        await websocket.send_json({
            'type': 'grid_size_update',
            'grid_size': state.get('grid_size')
        })

    if state.get('tokens'):
        await websocket.send_json({
            'type': 'tokens_init',
            'tokens': list(state['tokens'].values())
        })

    # Отправляем сохраненные рисунки при подключении
    if state.get('drawings'):
        await websocket.send_json({
            'type': 'draw_init',
            'drawings': state.get('drawings')
        })

    # 🆕 Отправляем Туман войны при подключении
    if state.get('fow_paths'):
        await websocket.send_json({
            'type': 'fow_sync',
            'fow_paths': state.get('fow_paths')
        })

    await broadcast_ws_event(room_id_str, {
        'type': 'player_join',
        'username': username,
        'char_name': char_name,
        'is_master': is_master
    })

    # 📡 4. Настройка подписки Redis Pub/Sub для этого клиента
    pubsub = utils.redis_client.pubsub()
    await pubsub.subscribe(f"room:{room_id_str}:channel")

    # 🕒 Отменяем таймер удаления чата, так как в комнате появился активный пользователь
    if utils.redis_client:
        await utils.redis_client.persist(f"room:{room_id_str}:chat_log")

    async def listen_to_redis():
        """Фоновая таска: слушает Redis и отправляет данные в этот конкретный сокет"""
        try:
            async for message in pubsub.listen():
                if message['type'] == 'message':
                    data = json.loads(message['data'])
                    await websocket.send_json(data)
        except asyncio.CancelledError:
            pass

    listener_task = asyncio.create_task(listen_to_redis())

    # 🔄 5. Основной цикл приёма сообщений от клиента
    try:
        while True:
            try:
                raw_data = await websocket.receive_json()
            except Exception as exc:
                print(f"⚠️ WS невалидное сообщение [{room_id}]: {exc}")
                await websocket.close(code=4400, reason="Invalid message")
                break

            msg_type = raw_data.get('type') if isinstance(raw_data, dict) else None

            # 🛡️ Pydantic-валидация входящего WS-сообщения
            schema_cls = WS_SCHEMAS.get(msg_type)
            if schema_cls is None:
                continue  # неизвестный тип — игнорируем (как и раньше)

            try:
                data = schema_cls(**raw_data).model_dump()
            except ValidationError as exc:
                print(f"⚠️ WS validation error [{room_id}] type={msg_type}: {exc.errors()}")
                continue

            if msg_type in ['map_update', 'map_clear', 'token_update', 'combatant_hp_update', 'grid_size_update',
                            'draw_line', 'draw_clear', 'fow_update', 'tokens_clear']:
                current_state = await get_redis_room_state(room_id_str)
            else:
                current_state = {}

            if msg_type == 'dice_roll':
                message = {
                    'type': 'dice_roll',
                    'username': username,
                    'char_name': char_name,
                    'is_master': is_master,
                    'name': data.get('name', ''),
                    'roll': data.get('roll'),
                    'sides': data.get('sides'),
                    'modifier': data.get('modifier', 0),
                    'total': data.get('total'),
                    'is_crit': data.get('is_crit', False),
                    'is_fail': data.get('is_fail', False),
                    'is_hidden': data.get('is_hidden', False),
                    'timestamp': time.time()
                }

                if utils.redis_client:
                    await utils.redis_client.rpush(f"room:{room_id_str}:chat_log", json.dumps(message))

                await broadcast_ws_event(room_id_str, message)

            elif msg_type == 'measure':
                await broadcast_ws_event(room_id_str, {
                    'type': 'measure',
                    'username': username,
                    'start': data.get('start'),
                    'end': data.get('end'),
                    'color': '#c9a961' if is_master else '#3498db'
                })

            elif msg_type == 'chat_message':
                chat_msg = {
                    "type": "chat_message",
                    "text": data.get("text", ""),
                    "username": username,
                    "char_name": char_name,
                    "is_master": is_master,
                    "timestamp": time.time()
                }

                if utils.redis_client:
                    await utils.redis_client.rpush(f"room:{room_id_str}:chat_log", json.dumps(chat_msg))

                await broadcast_ws_event(room_id_str, chat_msg)

            elif msg_type == 'grid_size_update' and is_master:
                grid_size = data.get('grid_size', 50)
                current_state['grid_size'] = grid_size
                await save_redis_room_state(room_id_str, current_state)

                await broadcast_ws_event(room_id_str, {
                    'type': 'grid_size_update',
                    'grid_size': grid_size
                })

            elif msg_type == 'draw_line':
                if 'drawings' not in current_state:
                    current_state['drawings'] = []
                line_data = data.get('line')
                if line_data:
                    current_state['drawings'].append(line_data)
                    await save_redis_room_state(room_id_str, current_state)
                    await broadcast_ws_event(room_id_str, {
                        'type': 'draw_line',
                        'line': line_data
                    })

            elif msg_type == 'draw_clear':
                current_state['drawings'] = []
                await save_redis_room_state(room_id_str, current_state)
                await broadcast_ws_event(room_id_str, {'type': 'draw_clear'})

            elif msg_type == 'fow_update' and is_master:
                action = data.get('action')
                if 'fow_paths' not in current_state:
                    current_state['fow_paths'] = []

                if action == 'add_path':
                    current_state['fow_paths'].append(data.get('path'))
                elif action == 'hide_all':
                    current_state['fow_paths'] = [{'type': 'hide_all'}]
                elif action == 'clear_all':
                    current_state['fow_paths'] = []

                await save_redis_room_state(room_id_str, current_state)
                await broadcast_ws_event(room_id_str, {
                    'type': 'fow_sync',
                    'fow_paths': current_state['fow_paths']
                })

            elif msg_type == 'tokens_clear' and is_master:
                current_state['tokens'] = {}
                current_state['combatants'] = []
                await save_redis_room_state(room_id_str, current_state)
                await broadcast_ws_event(room_id_str, {'type': 'tokens_clear'})

            elif msg_type == 'map_update' and is_master:
                current_state['map_image'] = data.get('image')
                current_state['map_width'] = data.get('width', 0)
                current_state['map_height'] = data.get('height', 0)
                await save_redis_room_state(room_id_str, current_state)

                await broadcast_ws_event(room_id_str, {
                    'type': 'map_update',
                    'image': data.get('image'),
                    'width': data.get('width', 0),
                    'height': data.get('height', 0),
                    'username': username,
                    'char_name': char_name
                })

            elif msg_type == 'map_clear' and is_master:
                current_state['map_image'] = None
                current_state['map_width'] = 0
                current_state['map_height'] = 0
                current_state['drawings'] = []
                current_state['fow_paths'] = []
                await save_redis_room_state(room_id_str, current_state)
                await broadcast_ws_event(room_id_str, {
                    'type': 'map_clear',
                    'username': username,
                    'char_name': char_name
                })

            elif msg_type == 'token_update':
                action = data.get('action')
                token_data = data.get('token', {})

                token_id = str(
                    token_data.get('char_id') or
                    token_data.get('token_id') or
                    data.get('char_id') or
                    data.get('token_id') or
                    f"token_{uuid.uuid4().hex}"
                )

                # 🛡️ Игрок управляет только токеном своего персонажа;
                # чужие/новые токены (монстры, объекты, другие игроки) — только мастер.
                owner_id = str(token_data.get('char_id') or token_data.get('token_id') or token_id or '')
                if not is_master and owner_id not in owned_char_ids:
                    print(f"⛔ Отказ token_update({action}) игроку {username} (room {room_id_str})")
                    continue

                token_data['char_id'] = token_id
                token_data['token_id'] = token_id

                if 'combatants' not in current_state:
                    current_state['combatants'] = []

                if action == 'add':
                    if 'tokens' not in current_state:
                        current_state['tokens'] = {}
                    current_state['tokens'][token_id] = token_data

                    # 🆕 НОВОЕ: Развилка для предметов (is_object)
                    if token_data.get('is_object'):
                        # Сохраняем состояние и рассылаем токен без добавления в трекер боя
                        await save_redis_room_state(room_id_str, current_state)
                        await broadcast_ws_event(room_id_str, {
                            'type': 'token_add',
                            'token': token_data
                        })
                    else:
                        # Старая логика для персонажей и монстров
                        import random
                        initiative = token_data.get('initiative')
                        if initiative is None:
                            dex_mod = token_data.get('dex_mod', 0)
                            initiative = random.randint(1, 20) + dex_mod
                            token_data['initiative'] = initiative

                        combatant = {
                            'token_id': token_id,
                            'name': token_data.get('name') or token_data.get('char_name', 'Неизвестно'),
                            'initiative': initiative,
                            'ac': token_data.get('ac') or token_data.get('armor_class') or '?',
                            'hp_current': token_data.get('hp_current'),
                            'hp_max': token_data.get('hp_max'),
                            'image': token_data.get('image'),
                            'is_monster': token_data.get('is_monster', False)
                        }

                        current_state['combatants'] = [c for c in current_state['combatants'] if c['token_id'] != token_id]
                        current_state['combatants'].append(combatant)
                        current_state['combatants'].sort(key=lambda x: x['initiative'], reverse=True)

                        await save_redis_room_state(room_id_str, current_state)

                        await broadcast_ws_event(room_id_str, {
                            'type': 'combat_update',
                            'combatants': current_state['combatants']
                        })
                        await broadcast_ws_event(room_id_str, {
                            'type': 'token_add',
                            'token': token_data
                        })

                elif action == 'remove':
                    if 'tokens' in current_state and token_id in current_state['tokens']:
                        removed_token = current_state['tokens'][token_id]
                        is_monster = removed_token.get('is_monster', False)
                        token_name = removed_token.get('name') or removed_token.get('char_name', 'Неизвестно')

                        del current_state['tokens'][token_id]

                        # 🆕 НОВОЕ: Обновляем бой только если токен там был
                        if 'combatants' in current_state:
                            old_len = len(current_state['combatants'])
                            current_state['combatants'] = [c for c in current_state['combatants'] if
                                                           c['token_id'] != token_id]
                            if len(current_state['combatants']) != old_len:
                                await broadcast_ws_event(room_id_str, {
                                    'type': 'combat_update',
                                    'combatants': current_state['combatants']
                                })

                        await save_redis_room_state(room_id_str, current_state)

                        await broadcast_ws_event(room_id_str, {
                            'type': 'token_remove',
                            'char_id': token_id,
                            'token_id': token_id,
                            'is_monster': is_monster,
                            'name': token_name
                        })


                elif action == 'move':

                    if 'tokens' in current_state and token_id in current_state['tokens']:

                        current_state['tokens'][token_id]['x'] = token_data.get('x')

                        current_state['tokens'][token_id]['y'] = token_data.get('y')

                        # 🆕 Сохраняем ширину и высоту, если они переданы (для масштабирования пропсов)

                        if token_data.get('width') is not None:
                            current_state['tokens'][token_id]['width'] = token_data.get('width')

                        if token_data.get('height') is not None:
                            current_state['tokens'][token_id]['height'] = token_data.get('height')

                        await save_redis_room_state(room_id_str, current_state)

                        await broadcast_ws_event(room_id_str, {

                            'type': 'token_move',

                            'token': token_data

                        })

            elif msg_type == 'combatant_hp_update':
                token_id = data.get('token_id')
                new_hp = data.get('hp_current')

                # 🛡️ HP меняет мастер (любой токен) или владелец персонажа
                if not is_master and (token_id is None or str(token_id) not in owned_char_ids):
                    print(f"⛔ Отказ combatant_hp_update игроку {username} (room {room_id_str})")
                    continue

                if token_id and new_hp is not None:
                    if 'combatants' in current_state:
                        for combatant in current_state['combatants']:
                            if str(combatant.get('token_id')) == str(token_id) or str(combatant.get('char_id')) == str(token_id):
                                combatant['hp_current'] = new_hp
                                break

                        await save_redis_room_state(room_id_str, current_state)
                        await broadcast_ws_event(room_id_str, {
                            'type': 'combat_update',
                            'combatants': current_state['combatants']
                        })

                    await broadcast_ws_event(room_id_str, {
                        'type': 'hp_update',
                        'char_id': token_id,
                        'hp_current': new_hp
                    })

    except WebSocketDisconnect:
        pass

    except Exception as e:
        print(f"❌ WebSocket error [{room_id}]: {e}")

    finally:
        listener_task.cancel()
        if utils.redis_client:
            await pubsub.unsubscribe(f"room:{room_id_str}:channel")
        player_connections[conn_key] -= 1

        if not is_master:
            async def delayed_leave(rid, uname, cname, key):
                await asyncio.sleep(60)
                if player_connections.get(key, 0) <= 0:
                    try:
                        rooms_data = load_rooms()
                        room_db = next((r for r in rooms_data['rooms'] if str(r['id']) == rid), None)
                        if room_db:
                            room_db['current_players'] = [
                                p for p in room_db.get('current_players', [])
                                if p.get('username') != uname
                            ]
                            save_rooms(rooms_data)
                    except Exception as e:
                        print(f"❌ Ошибка удаления игрока из БД: {e}")

                    await broadcast_ws_event(rid, {
                        'type': 'player_leave',
                        'username': uname,
                        'char_name': cname
                    })

            asyncio.create_task(delayed_leave(room_id_str, username, char_name, conn_key))

        if utils.redis_client:
            await asyncio.sleep(0.5)
            try:
                subs = await utils.redis_client.pubsub_numsub(f"room:{room_id_str}:channel")
                active_connections = 1
                if isinstance(subs, list) and len(subs) > 0:
                    active_connections = subs[0][1]
                elif isinstance(subs, dict):
                    active_connections = list(subs.values())[0]

                if active_connections == 0:
                    await utils.redis_client.expire(f"room:{room_id_str}:chat_log", 3600)
            except Exception as e:
                print(f"⚠️ Ошибка установки TTL для чата: {e}")