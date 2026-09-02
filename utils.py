import json
import os
import re
import random
import string
import time
import uuid
from typing import Dict, List, Any, Optional
from pathlib import Path
from datetime import datetime

import boto3
import psycopg2
from psycopg2.extras import RealDictCursor
import redis.asyncio as redis
from fastapi import UploadFile

from config import settings

# ============================================================
# === КОНСТАНТЫ ===
# ============================================================

# XP Thresholds D&D 5e (уровни 1-20)
XP_THRESHOLDS = [
    0, 300, 900, 2700, 6500, 14000, 23000, 34000, 48000, 64000,
    85000, 100000, 120000, 140000, 165000, 195000, 225000, 265000, 305000, 355000
]

# Глобальные хранилища статических данных
CLASSES_DATA: Dict[str, dict] = {}
EQUIPMENT_DATA: Dict[str, Any] = {}
SPELLS_DATA: List[dict] = []

# ============================================================
# === REDIS CONNECTION ===
# ============================================================

redis_client: Optional[redis.Redis] = None


async def init_redis():
    """Инициализация пула соединений с Redis"""
    global redis_client
    redis_client = redis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB,
        password=settings.REDIS_PASSWORD,
        decode_responses=True  # Автоматически декодирует байты в строки
    )


async def close_redis():
    """Закрытие соединений с Redis"""
    global redis_client
    if redis_client:
        await redis_client.aclose()


def _default_room_state() -> dict:
    """Базовое состояние пустой VTT-комнаты"""
    return {
        'map_image': None,
        'map_width': 0,
        'map_height': 0,
        'tokens': {},
        'selected_monsters': [],
        'combatants': []
    }


async def get_redis_room_state(room_id: str) -> dict:
    """Получает текущее состояние VTT-комнаты из Redis"""
    if not redis_client:
        return _default_room_state()
    data = await redis_client.get(f"room:{room_id}:state")
    if data:
        return json.loads(data)
    return _default_room_state()


async def save_redis_room_state(room_id: str, state: dict) -> None:
    """Сохраняет состояние VTT-комнаты в Redis"""
    if redis_client:
        await redis_client.set(f"room:{room_id}:state", json.dumps(state))


# ============================================================
# === DB CONNECTION ===
# ============================================================

def get_db_connection():
    """Возвращает соединение с БД PostgreSQL."""
    conn = psycopg2.connect(
        dbname=settings.DB_NAME,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD.get_secret_value(),
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        connect_timeout=5
    )
    psycopg2.extras.register_default_jsonb(conn, loads=json.loads)
    return conn


def get_all_spells() -> list:
    """Возвращает список всех заклинаний из БД"""
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM spells ORDER BY level, name_ru")
                return [dict(row) for row in cur.fetchall()]
    except Exception as e:
        print(f"❌ Ошибка при получении заклинаний: {e}")
        return []


def get_all_monsters() -> list:
    """Возвращает список всех монстров из базы данных."""
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM monsters ORDER BY name")
                monsters = []
                for row in cur.fetchall():
                    m = dict(row)
                    # Совместимость с фронтендом бестиария (master_prep.html):
                    # attributes -> stats, token_path -> token_image, meta -> description
                    m['stats'] = m.get('attributes') or {}
                    m['token_image'] = m.get('token_path')
                    m['description'] = m.get('meta') or ''
                    m['hit_points_clean'] = m.get('hit_points')
                    monsters.append(m)
                return monsters
    except Exception as e:
        print(f"❌ Ошибка при получении бестиария из БД: {e}")
        return []


def init_monsters_table():
    """Создаёт таблицу monsters, если её ещё нет (идемпотентно, БЕЗ очистки)."""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS monsters (
                        id SERIAL PRIMARY KEY,
                        name TEXT NOT NULL,
                        meta TEXT,
                        armor_class INTEGER,
                        hit_points INTEGER,
                        hit_dice TEXT,
                        speed TEXT,
                        attributes JSONB,
                        challenge_rating TEXT,
                        traits JSONB,
                        actions JSONB,
                        legendary_actions JSONB,
                        token_path TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                # Добавляем столбец token_path, если его ещё нет (для уже существующих таблиц)
                cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='monsters' AND column_name='token_path'")
                if not cur.fetchone():
                    cur.execute("ALTER TABLE monsters ADD COLUMN token_path TEXT")
                conn.commit()
    except Exception as e:
        print(f"❌ Ошибка инициализации таблицы monsters: {e}")


def _get_user_id(cur, username: str) -> Optional[int]:
    """Получает числовой ID пользователя по username."""
    cur.execute("SELECT id FROM users WHERE username = %s", (username,))
    user = cur.fetchone()
    if not user:
        return None
    if isinstance(user, dict):
        return user['id']
    return user[0]


def _safe_int(value, default: int = 0) -> int:
    """Безопасно приводит значение к int."""
    if value is None:
        return default
    if isinstance(value, int):
        return value
    try:
        match = re.search(r'-?\d+', str(value))
        if match:
            return int(match.group())
    except (ValueError, AttributeError):
        pass
    return default


# ============================================================
# === S3 (MinIO) CONNECTION ===
# ============================================================

s3_client = boto3.client(
    's3',
    endpoint_url=settings.S3_ENDPOINT,
    aws_access_key_id=settings.S3_ACCESS_KEY,
    aws_secret_access_key=settings.S3_SECRET_KEY.get_secret_value(),
    region_name='us-east-1'
)


def init_s3_bucket():
    """Создает бакет в MinIO/S3, если его еще нет, и настраивает публичный доступ"""
    try:
        s3_client.head_bucket(Bucket=settings.S3_BUCKET)
    except Exception:
        s3_client.create_bucket(Bucket=settings.S3_BUCKET)

        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "PublicRead",
                    "Effect": "Allow",
                    "Principal": "*",
                    "Action": ["s3:GetObject"],
                    "Resource": [f"arn:aws:s3:::{settings.S3_BUCKET}/*"]
                }
            ]
        }
        s3_client.put_bucket_policy(Bucket=settings.S3_BUCKET, Policy=json.dumps(policy))


# Разрешённые к загрузке изображения: расширение и MIME должны совпадать с белым списком.
ALLOWED_IMAGE_EXTS = {'png', 'jpg', 'jpeg', 'webp', 'gif'}
ALLOWED_IMAGE_TYPES = {'image/png', 'image/jpeg', 'image/gif', 'image/webp'}
DEFAULT_MAX_UPLOAD_SIZE = 5 * 1024 * 1024  # 5 МБ


async def upload_image_to_s3(
        file: UploadFile,
        prefix: str = "maps",
        max_size: int = DEFAULT_MAX_UPLOAD_SIZE
) -> str:
    """Загружает изображение в S3/MinIO с проверкой расширения, MIME и размера.

    Файл читается чанками, чтобы не держать в памяти больше max_size байт.
    При нарушении ограничений поднимается ValueError (роуты превращают его
    в JSON-ответ {status: 'error'}).
    """
    # --- 1. Расширение из имени файла (без учёта регистра и путей) ---
    raw_name = (file.filename or '').replace('\\', '/').split('/')[-1]
    ext = raw_name.rsplit('.', 1)[-1].lower() if '.' in raw_name else 'png'
    if ext not in ALLOWED_IMAGE_EXTS:
        raise ValueError("Неподдерживаемый формат файла. Допустимы: png, jpg, jpeg, webp, gif.")

    # --- 2. MIME-тип ---
    content_type = (file.content_type or '').lower()
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise ValueError("Неподдерживаемый MIME-тип изображения.")

    # --- 3. Чтение с ограничением размера ---
    chunks = []
    total = 0
    while True:
        chunk = await file.read(64 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_size:
            raise ValueError(f"Файл слишком большой (максимум {max_size // (1024 * 1024)} МБ).")
        chunks.append(chunk)
    if total == 0:
        raise ValueError("Пустой файл.")
    content = b"".join(chunks)

    filename = f"{prefix}/{uuid.uuid4().hex}.{ext}"
    s3_client.put_object(
        Bucket=settings.S3_BUCKET,
        Key=filename,
        Body=content,
        ContentType=content_type or 'image/png'
    )
    return f"/media/{filename}"


# ============================================================
# === SCENES (КАРТЫ) ===
# ============================================================

def init_scenes_table():
    """Инициализация таблицы для хранения сцен/карт"""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS scenes (
                    id SERIAL PRIMARY KEY,
                    room_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    background_url TEXT NOT NULL,
                    map_width INTEGER DEFAULT 1920,
                    map_height INTEGER DEFAULT 1080,
                    tokens JSONB DEFAULT '[]'::jsonb,
                    drawings JSONB DEFAULT '[]'::jsonb,
                    fog_of_war JSONB DEFAULT '[]'::jsonb,
                    is_active BOOLEAN DEFAULT false,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.commit()


def get_room_scenes(room_id: int) -> list:
    """Получает все сцены конкретной комнаты"""
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM scenes WHERE room_id = %s ORDER BY created_at ASC", (room_id,))
            return [dict(row) for row in cur.fetchall()]


def create_scene(room_id: int, name: str, background_url: str, width: int, height: int) -> dict:
    """Создает новую сцену в БД"""
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT COUNT(*) FROM scenes WHERE room_id = %s", (room_id,))
            count = cur.fetchone()['count']
            is_active = (count == 0)  # Первая сцена автоматически активна

            cur.execute("""
                INSERT INTO scenes (room_id, name, background_url, map_width, map_height, is_active)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING *;
            """, (room_id, name, background_url, width, height, is_active))
            conn.commit()
            return dict(cur.fetchone())


def set_active_scene(room_id: int, scene_id: int):
    """Делает выбранную сцену активной, отключая остальные в этой комнате"""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE scenes SET is_active = false WHERE room_id = %s", (room_id,))
            cur.execute("UPDATE scenes SET is_active = true WHERE id = %s AND room_id = %s", (scene_id, room_id))
            conn.commit()


def delete_scene(room_id: int, scene_id: int):
    """Удаляет сцену из БД и картинку из S3"""
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Сначала получаем данные о сцене, чтобы знать, что удалять из S3
            cur.execute("SELECT background_url, is_active FROM scenes WHERE id = %s AND room_id = %s",
                        (scene_id, room_id))
            scene = cur.fetchone()
            if not scene:
                return None

            # Удаляем запись из БД
            cur.execute("DELETE FROM scenes WHERE id = %s AND room_id = %s", (scene_id, room_id))
            conn.commit()

            # Удаляем файл из S3 (MinIO)
            try:
                key = scene['background_url'].replace('/media/', '')
                s3_client.delete_object(Bucket=settings.S3_BUCKET, Key=key)
            except Exception as e:
                print(f"Ошибка удаления файла из S3: {e}")

            return scene


# ============================================================
# === FILE I/O ===
# ============================================================

def get_random_quote():
    """Считывает цитаты и возвращает случайную."""
    quotes_file = Path("data/quotes.json")
    if quotes_file.exists():
        try:
            with open(quotes_file, "r", encoding="utf-8") as f:
                quotes = json.load(f)
                if isinstance(quotes, list) and len(quotes) > 0:
                    return random.choice(quotes).get("text", "")
        except Exception:
            pass
    return "Не все те, кто странствуют — потеряны."


# ============================================================
# === БАЗОВЫЕ УТИЛИТЫ ===
# ============================================================

def calc_modifier(score: int) -> int:
    return (score - 10) // 2


def calc_level_from_xp(xp: int) -> int:
    for level in range(20, 0, -1):
        if xp >= XP_THRESHOLDS[level - 1]:
            return level
    return 1


def calc_prof_bonus(level: int) -> int:
    if level < 1:
        return 2
    return 2 + (level - 1) // 4


def get_level_progress(xp: int, level: int) -> float:
    if level >= 20:
        return 100.0
    curr = XP_THRESHOLDS[level - 1]
    nxt = XP_THRESHOLDS[level]
    return min(100.0, max(0.0, ((xp - curr) / (nxt - curr)) * 100))


# ============================================================
# === ВЕС И ГРУЗОПОДЪЁМНОСТЬ ===
# ============================================================

def parse_weight(weight_str) -> float:
    if not weight_str or not isinstance(weight_str, str):
        return 0.0
    s = weight_str.lower().replace('фнт.', '').replace('фнт', '').strip()
    if not s: return 0.0
    s = s.replace('½', '0.5').replace('¼', '0.25').replace('¾', '0.75').replace(',', '.')
    try:
        match = re.search(r'[\d.]+', s)
        if match: return float(match.group())
    except (ValueError, AttributeError):
        pass
    return 0.0


def calculate_total_weight(char: dict) -> float:
    inv = char.get('inventory', {})
    total = 0.0
    for w in inv.get('weapons', []): total += parse_weight(w.get('weight'))
    for a in inv.get('armor', []): total += parse_weight(a.get('weight'))
    for g in inv.get('gear', []):
        qty = g.get('qty', 1) or 1
        total += parse_weight(g.get('weight')) * qty
    coins = inv.get('coins', {})
    total_coins = sum(coins.values()) if isinstance(coins, dict) else 0
    total += total_coins / 50.0
    for a in inv.get('arrows', []): total += (a.get('qty', 0) or 0) / 20.0
    for b in inv.get('bolts', []): total += (b.get('qty', 0) or 0) / 20.0
    return round(total, 2)


def calculate_carry_capacity(char: dict) -> dict:
    str_score = 10
    if isinstance(char.get('stats', {}).get('STR'), dict):
        str_score = char['stats']['STR'].get('score', 10)
    elif isinstance(char.get('stats', {}).get('STR'), int):
        str_score = char['stats']['STR']

    current_weight = calculate_total_weight(char)
    max_capacity = str_score * 15
    push_drag_lift = str_score * 30
    threshold_light, threshold_medium, threshold_heavy = str_score * 5, str_score * 10, str_score * 15

    encumbrance_level, encumbrance_name, speed_penalty, has_disadvantage = 0, "Свободен", 0, False
    if current_weight > threshold_heavy:
        encumbrance_level, encumbrance_name, speed_penalty, has_disadvantage = 3, "Неподвижен", 999, True
    elif current_weight > threshold_medium:
        encumbrance_level, encumbrance_name, speed_penalty, has_disadvantage = 2, "Сильно нагружен", 20, True
    elif current_weight > threshold_light:
        encumbrance_level, encumbrance_name, speed_penalty, has_disadvantage = 1, "Нагружен", 10, False

    return {
        'strength': str_score, 'max_capacity': max_capacity, 'push_drag_lift': push_drag_lift,
        'current_weight': current_weight, 'encumbrance_level': encumbrance_level,
        'encumbrance_name': encumbrance_name, 'speed_penalty': speed_penalty,
        'has_disadvantage': has_disadvantage,
        'thresholds': {'light': threshold_light, 'medium': threshold_medium, 'heavy': threshold_heavy,
                       'max': push_drag_lift}
    }


# ============================================================
# === USERS ===
# ============================================================

def load_users() -> Dict[str, dict]:
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM users")
            return {user['username']: dict(user) for user in cur.fetchall()}


def save_users(users: Dict[str, dict]) -> None:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            for username, data in users.items():
                cur.execute("""
                    INSERT INTO users (username, password_hash, role)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (username) DO UPDATE SET
                        password_hash = EXCLUDED.password_hash,
                        role = EXCLUDED.role
                """, (username, data.get('password_hash', ''), data.get('role', 'player')))
            conn.commit()


def load_user_profile(username: str) -> dict:
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM users WHERE username = %s", (username,))
            user = cur.fetchone()
            if not user:
                return {'username': username, 'joined_rooms': [], 'created_at': datetime.now().isoformat()}

            cur.execute("""
                SELECT room_id 
                FROM room_players 
                WHERE user_id = %s 
                ORDER BY last_active DESC NULLS LAST
                LIMIT 10
            """, (user['id'],))

            joined_rooms = [str(row['room_id']) for row in cur.fetchall()]

            profile = dict(user)
            profile['joined_rooms'] = joined_rooms
            return profile


def save_user_profile(username: str, profile: dict) -> None:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            user_id = _get_user_id(cur, username)
            if not user_id: return

            cur.execute("SELECT room_id FROM room_players WHERE user_id = %s", (user_id,))
            db_rooms = {str(row['room_id']) for row in cur.fetchall()}
            new_rooms = set(str(r) for r in profile.get('joined_rooms', []))

            for room_id in (new_rooms - db_rooms):
                try:
                    cur.execute("INSERT INTO room_players (room_id, user_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                                (int(room_id), user_id))
                except ValueError:
                    pass

            to_remove = db_rooms - new_rooms
            if to_remove:
                try:
                    cur.execute("DELETE FROM room_players WHERE user_id = %s AND room_id = ANY(%s)",
                                (user_id, [int(r) for r in to_remove]))
                except ValueError:
                    pass
            conn.commit()


def add_room_to_player_history(username: str, room_id: str) -> None:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            user_id = _get_user_id(cur, username)
            if not user_id: return
            try:
                cur.execute("""
                    INSERT INTO room_players (room_id, user_id, joined_at, last_active)
                    VALUES (%s, %s, NOW(), NOW())
                    ON CONFLICT (room_id, user_id) DO UPDATE SET last_active = NOW()
                """, (int(room_id), user_id))
                conn.commit()
            except ValueError:
                pass


# ============================================================
# === ROOMS ===
# ============================================================

def load_rooms() -> dict:
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT r.*, u.username as master_username 
                FROM rooms r 
                JOIN users u ON r.master_id = u.id
            """)
            rooms = []
            for row in cur.fetchall():
                room = dict(row)
                room['master_id'] = room.pop('master_username')

                cur.execute("""
                    SELECT u.username, rp.last_active, rp.character_id, rp.char_name
                    FROM room_players rp 
                    JOIN users u ON u.id = rp.user_id
                    WHERE rp.room_id = %s
                """, (room['id'],))
                players = cur.fetchall()

                room['current_players'] = [
                    {
                        'username': p['username'],
                        'last_active': p['last_active'].timestamp() if p['last_active'] else 0,
                        'char_id': p['character_id'],
                        'char_name': p['char_name']
                    }
                    for p in players
                ]
                rooms.append(room)
            return {"rooms": rooms}


def save_rooms(data: dict) -> None:
    rooms = data.get("rooms", [])
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            for room in rooms:
                room_id = room.get('id')
                map_data = json.dumps(room.get('map_data')) if room.get('map_data') else None
                tokens = json.dumps(room.get('tokens')) if room.get('tokens') else None

                try:
                    db_room_id = int(room_id) if room_id else None
                except (ValueError, TypeError):
                    db_room_id = None

                if db_room_id:
                    cur.execute("""
                        UPDATE rooms SET name=%s, description=%s, max_players=%s, 
                                         map_data=%s::jsonb, tokens=%s::jsonb, active=%s
                        WHERE id=%s
                    """, (room['name'], room.get('description'), room.get('max_players', 6),
                          map_data, tokens, room.get('active', True), db_room_id))
                else:
                    master_id = room.get('master_id')
                    if master_id and not isinstance(master_id, int):
                        try:
                            master_id = int(master_id)
                        except (ValueError, TypeError):
                            master_username = str(master_id)
                            master_id = _get_user_id(cur, master_username)

                    if not master_id:
                        master_username = room.get('master')
                        if master_username:
                            master_id = _get_user_id(cur, master_username)

                    if not master_id:
                        print(f"⚠️ Не удалось найти master_id для комнаты {room.get('name')}")
                        continue

                    try:
                        master_id = int(master_id)
                    except (ValueError, TypeError):
                        print(f"⚠️ master_id не является числом: {master_id}")
                        continue

                    cur.execute("""
                        INSERT INTO rooms (master_id, name, description, invite_code, max_players, map_data, tokens, active)
                        VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s) RETURNING id
                    """, (master_id, room['name'], room.get('description'),
                          room.get('invite_code', generate_invite_code()),
                          room.get('max_players', 6), map_data, tokens, room.get('active', True)))
                    room['id'] = cur.fetchone()[0]
                    db_room_id = room['id']

                if db_room_id and 'current_players' in room:
                    cur.execute("DELETE FROM room_players WHERE room_id = %s", (db_room_id,))
                    for p in room['current_players']:
                        username = p.get('username')
                        if not username:
                            continue

                        user_id = _get_user_id(cur, username)
                        if not user_id:
                            continue

                        char_id = p.get('char_id')
                        char_name = p.get('char_name', '')
                        last_active = p.get('last_active')

                        if last_active:
                            cur.execute("""
                                INSERT INTO room_players (room_id, user_id, character_id, char_name, last_active)
                                VALUES (%s, %s, %s, %s, to_timestamp(%s))
                            """, (db_room_id, user_id, char_id, char_name, last_active))
                        else:
                            cur.execute("""
                                INSERT INTO room_players (room_id, user_id, character_id, char_name)
                                VALUES (%s, %s, %s, %s)
                            """, (db_room_id, user_id, char_id, char_name))

            conn.commit()


def generate_invite_code() -> str:
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))


def cleanup_inactive_players(room_id: str, timeout: int = 30) -> None:
    try:
        db_room_id = int(room_id)
    except (ValueError, TypeError):
        return

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                DELETE FROM room_players 
                WHERE room_id = %s AND last_active < NOW() - INTERVAL '%s seconds'
            """, (db_room_id, timeout))
            conn.commit()


# ============================================================
# === CHARACTERS ===
# ============================================================

def normalize_char(char: dict) -> dict:
    inv = char.get('inventory', {})
    if isinstance(inv, list):
        inv = {"weapons": [], "armor": [], "gear": [], "arrows": [], "bolts": [],
               "coins": {"cp": 0, "sp": 0, "ep": 0, "gp": 0, "pp": 0}, "items": inv, "known_spells": []}
    else:
        for key in ["weapons", "armor", "gear", "arrows", "bolts", "known_spells"]: inv.setdefault(key, [])
        inv.setdefault("coins", {"cp": 0, "sp": 0, "ep": 0, "gp": 0, "pp": 0})
    char['inventory'] = inv

    char.setdefault('description', '')
    char.setdefault('features_spells', '')
    char.setdefault('subclass', 'Нет')
    char.setdefault('_calculated_ac', None)
    char.setdefault('token_image', '')

    for field in ['description_appearance', 'description_background', 'description_allies',
                  'description_personality', 'description_ideals', 'description_bonds', 'description_flaws']:
        char.setdefault(field, '')
    char.setdefault('description_image', None)

    char.setdefault('physical', {})
    for k in ['height', 'weight', 'hair', 'eyes']: char['physical'].setdefault(k, '')

    char.setdefault('attributes', {})
    char['attributes'].setdefault('speed', 30)
    char['attributes'].setdefault('initiative', 0)
    char['attributes'].setdefault('prof_bonus', '+2')
    try:
        base_speed = int(char['attributes'].get('speed', 30))
    except (ValueError, TypeError):
        base_speed = 30
    char['attributes']['speed'] = base_speed

    char.setdefault('hp', {})
    char['hp'].setdefault('current', 10)
    char['hp'].setdefault('max', 10)
    char['hp'].setdefault('temp', 0)

    for stat_key in ["STR", "DEX", "CON", "INT", "WIS", "CHA"]:
        if stat_key not in char.get('stats', {}):
            char.setdefault('stats', {})[stat_key] = {'score': 10, 'modifier': 0}
        elif isinstance(char['stats'][stat_key], int):
            score = char['stats'][stat_key]
            char['stats'][stat_key] = {'score': score, 'modifier': calc_modifier(score)}

    char['attributes']['initiative'] = char['stats']['DEX']['modifier']
    level = char.get('level', 1)
    char['attributes']['prof_bonus'] = f"+{calc_prof_bonus(level)}"

    carry = calculate_carry_capacity(char)
    char['_carry'] = carry
    char['attributes']['effective_speed'] = max(0, base_speed - carry['speed_penalty'])
    char['_calculated_ac'] = calculate_ac(char)
    return char


def recalc_char(char: dict) -> dict:
    if 'xp' in char: char['level'] = calc_level_from_xp(char['xp'])
    level = char.get('level', 1)
    char.setdefault('attributes', {})
    char['attributes']['prof_bonus'] = f"+{calc_prof_bonus(level)}"
    return char


def _fetch_character_details(cur, char_id: int) -> dict:
    details = {
        'stats': {}, 'skills': [], 'saving_throws': [],
        'inventory': {'weapons': [], 'armor': [], 'gear': [], 'arrows': [], 'bolts': [],
                      'coins': {'cp': 0, 'sp': 0, 'ep': 0, 'gp': 0, 'pp': 0}, 'known_spells': []}
    }

    cur.execute("SELECT stat_name, score, modifier FROM character_stats WHERE character_id = %s", (char_id,))
    for row in cur.fetchall(): details['stats'][row['stat_name']] = {'score': row['score'], 'modifier': row['modifier']}

    cur.execute("SELECT skill_key FROM character_skills WHERE character_id = %s", (char_id,))
    details['skills'] = [row['skill_key'] for row in cur.fetchall()]

    cur.execute("SELECT save_key FROM character_saving_throws WHERE character_id = %s", (char_id,))
    details['saving_throws'] = [row['save_key'] for row in cur.fetchall()]

    for table, key in [('character_weapons', 'weapons'), ('character_armor', 'armor'), ('character_gear', 'gear')]:
        cur.execute(f"SELECT * FROM {table} WHERE character_id = %s", (char_id,))
        details['inventory'][key] = [dict(row) for row in cur.fetchall()]

    cur.execute("SELECT * FROM character_ammo WHERE character_id = %s", (char_id,))
    for row in cur.fetchall():
        if row['type'] == 'arrows':
            details['inventory']['arrows'].append(dict(row))
        else:
            details['inventory']['bolts'].append(dict(row))

    cur.execute("SELECT * FROM character_coins WHERE character_id = %s", (char_id,))
    coins_row = cur.fetchone()
    if coins_row:
        details['inventory']['coins'] = {k: coins_row[k] for k in ['cp', 'sp', 'ep', 'gp', 'pp']}

    cur.execute("SELECT spell_name FROM character_known_spells WHERE character_id = %s", (char_id,))
    details['inventory']['known_spells'] = [row['spell_name'] for row in cur.fetchall()]
    return details


def load_chars(username: str) -> List[dict]:
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            user_id = _get_user_id(cur, username)
            if not user_id: return []

            cur.execute("SELECT * FROM characters WHERE user_id = %s", (user_id,))
            result = []
            for row in cur.fetchall():
                char_dict = {
                    'id': row['id'], 'name': row['name'], 'race': row['race'], 'char_class': row['char_class'],
                    'subclass': row['subclass'], 'alignment': row['alignment'], 'level': row['level'], 'xp': row['xp'],
                    'physical': {k: row[k] or '' for k in ['height', 'weight', 'hair', 'eyes']},
                    'attributes': {k: row[k] for k in ['ac', 'initiative', 'speed', 'prof_bonus', 'effective_speed']},
                    'hp': {'current': row['hp_current'], 'max': row['hp_max'], 'temp': row['hp_temp']},
                    'description_appearance': row['description_appearance'] or '',
                    'description_background': row['description_background'] or '',
                    'description_allies': row['description_allies'] or '',
                    'description_personality': row['description_personality'] or '',
                    'description_ideals': row['description_ideals'] or '',
                    'description_bonds': row['description_bonds'] or '',
                    'description_flaws': row['description_flaws'] or '',
                    'token_image': row['token_image_path'] or '',
                    'description_image': row['description_image_path'],
                    'description': '', 'features_spells': ''
                }
                char_dict.update(_fetch_character_details(cur, row['id']))
                result.append(normalize_char(char_dict))
            return result


def _upsert_character(cur, user_id: int, char: dict) -> int:
    char_id = char.get('id')
    physical, attributes, hp = char.get('physical', {}), char.get('attributes', {}), char.get('hp', {})

    level = _safe_int(char.get('level', 1), 1)
    xp = _safe_int(char.get('xp', 0), 0)
    initiative = _safe_int(attributes.get('initiative', 0), 0)
    speed = _safe_int(attributes.get('speed', 30), 30)
    effective_speed = _safe_int(attributes.get('effective_speed', speed), speed)
    hp_current = _safe_int(hp.get('current', 10), 10)
    hp_max = _safe_int(hp.get('max', 10), 10)
    hp_temp = _safe_int(hp.get('temp', 0), 0)

    params = (
        user_id, char.get('name', 'Без имени'), char.get('race', 'Человек'), char.get('char_class', 'Воин'),
        char.get('subclass', 'Нет'), char.get('alignment', 'Истинно нейтральный'), level, xp,
        physical.get('height'), physical.get('weight'), physical.get('hair'), physical.get('eyes'),
        attributes.get('ac', '10'), initiative, speed,
        attributes.get('prof_bonus', '+2'), effective_speed,
        hp_current, hp_max, hp_temp,
        char.get('description_appearance', ''), char.get('description_background', ''),
        char.get('description_allies', ''),
        char.get('description_personality', ''), char.get('description_ideals', ''), char.get('description_bonds', ''),
        char.get('description_flaws', ''),
        char.get('token_image', ''), char.get('description_image')
    )

    is_valid_id = isinstance(char_id, int)

    if is_valid_id:
        update_params = params[1:] + (char_id, user_id)
        cur.execute("""
            UPDATE characters SET 
                name=%s, race=%s, char_class=%s, subclass=%s, alignment=%s, level=%s, xp=%s,
                height=%s, weight=%s, hair=%s, eyes=%s, ac=%s, initiative=%s, speed=%s, prof_bonus=%s, effective_speed=%s,
                hp_current=%s, hp_max=%s, hp_temp=%s, description_appearance=%s, description_background=%s, description_allies=%s,
                description_personality=%s, description_ideals=%s, description_bonds=%s, description_flaws=%s,
                token_image_path=%s, description_image_path=%s, updated_at=NOW()
            WHERE id=%s AND user_id=%s RETURNING id
        """, update_params)
        res = cur.fetchone()
        if not res:
            is_valid_id = False
        else:
            char_id = res['id']

    if not is_valid_id:
        cur.execute("""
            INSERT INTO characters (
                user_id, name, race, char_class, subclass, alignment, level, xp, height, weight, hair, eyes,
                ac, initiative, speed, prof_bonus, effective_speed, hp_current, hp_max, hp_temp,
                description_appearance, description_background, description_allies, description_personality,
                description_ideals, description_bonds, description_flaws, token_image_path, description_image_path
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
        """, params)
        char_id = cur.fetchone()['id']

    for table in ['character_stats', 'character_skills', 'character_saving_throws',
                  'character_weapons', 'character_armor', 'character_gear', 'character_ammo', 'character_known_spells']:
        cur.execute(f"DELETE FROM {table} WHERE character_id = %s", (char_id,))

    for stat_name, stat_data in char.get('stats', {}).items():
        cur.execute("INSERT INTO character_stats (character_id, stat_name, score, modifier) VALUES (%s, %s, %s, %s)",
                    (char_id, stat_name, stat_data['score'], stat_data['modifier']))

    for skill in char.get('skills', []):
        cur.execute("INSERT INTO character_skills (character_id, skill_key) VALUES (%s, %s)", (char_id, skill))

    for save_key in char.get('saving_throws', []):
        cur.execute("INSERT INTO character_saving_throws (character_id, save_key) VALUES (%s, %s)", (char_id, save_key))

    for w in char.get('inventory', {}).get('weapons', []):
        cur.execute("""INSERT INTO character_weapons (character_id, name, type, damage, ammo_type, description, proficient, cost, weight)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (char_id, w.get('name'), w.get('type', 'standard'), w.get('damage', '1d4'),
                     w.get('ammo_type'), w.get('description'), w.get('proficient', True), w.get('cost'),
                     w.get('weight')))

    for a in char.get('inventory', {}).get('armor', []):
        cur.execute("""INSERT INTO character_armor (character_id, name, ac, stealth, strength_req, equipped, cost, weight, description)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (char_id, a.get('name'), a.get('ac', '10'), a.get('stealth'),
                     a.get('strength_req'), a.get('equipped', False), a.get('cost'), a.get('weight'),
                     a.get('description')))

    for g in char.get('inventory', {}).get('gear', []):
        cur.execute(
            "INSERT INTO character_gear (character_id, name, qty, cost, description, weight) VALUES (%s, %s, %s, %s, %s, %s)",
            (char_id, g.get('name'), g.get('qty', 1), g.get('cost'), g.get('description'), g.get('weight')))

    for ammo_list, ammo_type in [('arrows', 'arrows'), ('bolts', 'bolts')]:
        for am in char.get('inventory', {}).get(ammo_list, []):
            cur.execute(
                "INSERT INTO character_ammo (character_id, type, name, qty, extra_dmg) VALUES (%s, %s, %s, %s, %s)",
                (char_id, ammo_type, am.get('name', ammo_type), am.get('qty', 0), am.get('extra_dmg', 0)))

    coins = char.get('inventory', {}).get('coins', {})
    cur.execute("""INSERT INTO character_coins (character_id, cp, sp, ep, gp, pp) VALUES (%s, %s, %s, %s, %s, %s)
                   ON CONFLICT (character_id) DO UPDATE SET cp=EXCLUDED.cp, sp=EXCLUDED.sp, ep=EXCLUDED.ep, gp=EXCLUDED.gp, pp=EXCLUDED.pp""",
                (char_id, coins.get('cp', 0), coins.get('sp', 0), coins.get('ep', 0), coins.get('gp', 0),
                 coins.get('pp', 0)))

    for spell in char.get('inventory', {}).get('known_spells', []):
        cur.execute("INSERT INTO character_known_spells (character_id, spell_name) VALUES (%s, %s)", (char_id, spell))

    return char_id


def save_chars(username: str, chars: list) -> None:
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            user_id = _get_user_id(cur, username)
            if not user_id: return

            cur.execute("SELECT id FROM characters WHERE user_id = %s", (user_id,))
            existing_ids = {row['id'] for row in cur.fetchall()}
            current_ids = set()

            for char in chars:
                recalc_char(char)
                char_id = _upsert_character(cur, user_id, char)
                current_ids.add(char_id)

            to_delete = existing_ids - current_ids
            if to_delete:
                cur.execute("DELETE FROM characters WHERE id = ANY(%s) AND user_id = %s", (list(to_delete), user_id))
            conn.commit()


def parse_armor_ac(ac_raw):
    if not ac_raw:
        return 10, None, None

    ac_str = str(ac_raw).lower()

    base_match = re.search(r'\d+', ac_str)
    base_ac = int(base_match.group()) if base_match else 10

    mod_stat = None
    if 'лов' in ac_str:
        mod_stat = 'Лов'
    elif 'сил' in ac_str:
        mod_stat = 'Сил'

    mod_limit = None
    if 'макс' in ac_str:
        limit_match = re.search(r'макс\s*(\d+)', ac_str)
        if limit_match:
            mod_limit = int(limit_match.group(1))

    return base_ac, mod_stat, mod_limit


def parse_strength_req(req_raw):
    if not req_raw or str(req_raw).lower() in ['none', 'нет', '—', 'null']:
        return None

    match = re.search(r'\d+', str(req_raw))
    return int(match.group()) if match else None


def calculate_ac(char: dict) -> int:
    base_ac = 10
    dex_mod = char.get('stats', {}).get('DEX', {}).get('modifier', 0)
    char_class = char.get('char_class', '')

    equipped_armor = None
    equipped_shield = None

    for item in char.get('inventory', {}).get('armor', []):
        if item.get('equipped'):
            if 'ac_bonus' in item or str(item.get('category')).lower() == 'shield' or item.get('name') == 'Щит':
                equipped_shield = item
            else:
                equipped_armor = item

    if equipped_armor:
        ac_raw = str(equipped_armor.get('ac', '10'))

        if '+' in ac_raw and 'Лов' in ac_raw:
            try:
                base = int(ac_raw.split('+')[0].strip())
            except ValueError:
                base = 10

            max_dex = 2 if 'макс. 2' in ac_raw else None
            ac = base + (min(dex_mod, max_dex) if max_dex is not None else dex_mod)
        elif ac_raw.isdigit():
            ac = int(ac_raw)
        else:
            ac = base_ac + dex_mod
    else:
        if char_class == 'Монах' and not equipped_shield:
            wis_mod = char.get('stats', {}).get('WIS', {}).get('modifier', 0)
            ac = base_ac + dex_mod + wis_mod
        elif char_class == 'Варвар':
            con_mod = char.get('stats', {}).get('CON', {}).get('modifier', 0)
            ac = base_ac + dex_mod + con_mod
        else:
            ac = base_ac + dex_mod

    if equipped_shield:
        shield_bonus = equipped_shield.get('ac_bonus', 2)
        try:
            ac += int(str(shield_bonus).replace('+', ''))
        except ValueError:
            ac += 2

    return ac


def prepare_skills_and_saves(char: dict) -> tuple:
    prof_str = str(char.get('attributes', {}).get('prof_bonus', '2')).replace('+', '').strip()
    prof = int(prof_str) if prof_str.isdigit() else 2
    abilities_map = {'STR': 'Сила', 'DEX': 'Ловкость', 'CON': 'Телосложение', 'INT': 'Интеллект', 'WIS': 'Мудрость',
                     'CHA': 'Харизма'}
    saves_abbr = {'Сила': 'Сил', 'Ловкость': 'Лов', 'Телосложение': 'Тел', 'Интеллект': 'Инт', 'Мудрость': 'Мдр',
                  'Харизма': 'Хар'}
    saves = []
    for stat_key, stat_name in abilities_map.items():
        mod = calc_modifier(char['stats'][stat_key]['score'])
        is_prof = stat_name in char.get('saving_throws', [])
        saves.append({'name': stat_name, 'abbr': saves_abbr[stat_name], 'mod': mod, 'proficient': is_prof,
                      'total': mod + (prof if is_prof else 0)})

    skills_data = [
        ("Атлетика", "STR", "Сил"), ("Акробатика", "DEX", "Лов"), ("Ловкость рук", "DEX", "Лов"),
        ("Скрытность", "DEX", "Лов"),
        ("Магия", "INT", "Инт"), ("История", "INT", "Инт"), ("Расследование", "INT", "Инт"), ("Религия", "INT", "Инт"),
        ("Природа", "INT", "Инт"),
        ("Уход за животными", "WIS", "Мдр"), ("Проницательность", "WIS", "Мдр"), ("Медицина", "WIS", "Мдр"),
        ("Внимательность", "WIS", "Мдр"), ("Выживание", "WIS", "Мдр"),
        ("Обман", "CHA", "Хар"), ("Запугивание", "CHA", "Хар"), ("Выступление", "CHA", "Хар"),
        ("Убеждение", "CHA", "Хар")
    ]
    skills = []
    for name, stat_key, abbr in skills_data:
        mod = calc_modifier(char['stats'][stat_key]['score'])
        is_prof = name in char.get('skills', [])
        skills.append(
            {'name': name, 'abbr': abbr, 'mod': mod, 'proficient': is_prof, 'total': mod + (prof if is_prof else 0)})
    return saves, skills


# ============================================================
# === COMBAT UTILITIES ===
# ============================================================

def parse_damage(dmg_str: str) -> str:
    if not dmg_str: return "1d4"
    match = re.search(r'(\d+)к(\d+)', dmg_str.replace(' ', ''))
    return f"{match.group(1)}d{match.group(2)}" if match else "1d4"


def map_weapon_type(props: Any) -> str:
    props_str = str(props).lower()
    if "боеприпас" in props_str: return "ammunition"
    if "метательное" in props_str: return "thrown"
    if "фехтовальное" in props_str: return "finesse"
    return "standard"


def roll_dice(dice_str: str) -> tuple:
    match = re.match(r'(\d+)d(\d+)([+-]\d+)?', dice_str.strip())
    if not match: return [1], 1, "1d1"
    count, sides, mod = int(match.group(1)), int(match.group(2)), int(match.group(3) or 0)
    rolls = [random.randint(1, sides) for _ in range(count)]
    total = sum(rolls) + mod
    return rolls, total, f"{'+'.join(map(str, rolls))}{f'{mod:+d}' if mod != 0 else ''}"


# ============================================================
# === CLASSES / EQUIPMENT / SPELLS ===
# ============================================================

def load_equipment() -> Dict[str, Any]:
    equipment = {
        "armor": {},
        "weapons": {},
        "gear": []
    }

    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:

                cur.execute("SELECT * FROM armor;")
                for row in cur.fetchall():
                    category = row['category']
                    if category not in equipment["armor"]:
                        equipment["armor"][category] = []

                    str_req_int = row.get("strength_req_int")
                    strength_requirement = f"Сил {str_req_int}" if str_req_int else None

                    item = {
                        "name": row["name"],
                        "cost": row["cost"],
                        "strength_requirement": strength_requirement,
                        "stealth": "Помеха" if row.get("stealth_disadvantage") else None,
                        "weight": row["weight"]
                    }

                    if category == "shield":
                        item["ac_bonus"] = row.get("base_ac", 2)
                    else:
                        base_ac = row.get("base_ac", 10)
                        mod_stat = row.get("ac_mod_stat")
                        mod_limit = row.get("ac_mod_limit")

                        if mod_stat and mod_limit:
                            item["ac"] = f"{base_ac} + модификатор {mod_stat} (макс. {mod_limit})"
                        elif mod_stat:
                            item["ac"] = f"{base_ac} + модификатор {mod_stat}"
                        else:
                            item["ac"] = str(base_ac)

                        item["base_ac"] = base_ac
                        item["ac_mod_stat"] = mod_stat
                        item["ac_mod_limit"] = mod_limit
                        item["strength_req_int"] = str_req_int

                    equipment["armor"][category].append(item)

                cur.execute("SELECT * FROM weapons;")
                for row in cur.fetchall():
                    category = row['category']
                    if category not in equipment["weapons"]:
                        equipment["weapons"][category] = []

                    item = {
                        "name": row["name"],
                        "cost": row["cost"],
                        "damage": row["damage_string"],
                        "weight": row["weight"],
                        "properties": row["properties"] if row["properties"] else []
                    }
                    equipment["weapons"][category].append(item)

                cur.execute("SELECT * FROM gear;")
                for row in cur.fetchall():
                    item = {
                        "name": row["name"],
                        "cost": row["cost"],
                        "weight": row["weight"]
                    }
                    equipment["gear"].append(item)

        return equipment

    except Exception as e:
        print(f"⚠️ Ошибка загрузки снаряжения из БД: {e}")
        return {"armor": {}, "weapons": {}, "gear": []}


def init_static_data():
    """Загружает статические данные для приложения, используя базу данных"""
    global CLASSES_DATA, EQUIPMENT_DATA, SPELLS_DATA

    CLASSES_DATA = {}
    EQUIPMENT_DATA = load_equipment()
    SPELLS_DATA = get_all_spells()


def determine_weapon_proficiency(char_class: str, weapon_category: str, weapon_name: str) -> bool:
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT proficiencies->>'weapons' AS weapons 
                FROM classes 
                WHERE name = %s
            """, (char_class,))
            row = cur.fetchone()

            if not row or not row.get('weapons'):
                return False

            prof_text = row['weapons'].lower()

    if 'воинское' in prof_text or 'все' in prof_text:
        return True
    if 'простое' in prof_text and weapon_category.startswith('simple_'):
        return True

    weapon_lower = weapon_name.lower()
    prof_keywords_map = {
        'кинжал': ['кинжал'], 'дротик': ['дротик'], 'праща': ['праща'], 'посох': ['посох', 'дубинка'],
        'арбалет': ['арбалет'], 'меч': ['меч', 'скимитар'], 'копьё': ['копьё'], 'булава': ['булава'],
        'молот': ['молот'], 'топор': ['топор']
    }

    for keyword, names in prof_keywords_map.items():
        if keyword in prof_text:
            if any(w in weapon_lower for w in names):
                return True

    return False


def get_class_features(char_class: str, subclass_name: str, level: int) -> List[dict]:
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            query = """
                SELECT 
                    f.name, 
                    f.description, 
                    cfm.granted_at_level AS level, 
                    'base' AS source
                FROM classes c
                JOIN class_feature_map cfm ON c.id = cfm.class_id
                JOIN features f ON cfm.feature_id = f.id
                WHERE c.name = %(class_name)s AND cfm.granted_at_level <= %(level)s

                UNION ALL

                SELECT 
                    f.name, 
                    f.description, 
                    sfm.granted_at_level AS level, 
                    'subclass' AS source
                FROM classes c
                JOIN subclasses s ON c.id = s.class_id
                JOIN subclass_feature_map sfm ON s.id = sfm.subclass_id
                JOIN features f ON sfm.feature_id = f.id
                WHERE c.name = %(class_name)s 
                  AND s.name = %(subclass_name)s 
                  AND sfm.granted_at_level <= %(level)s

                ORDER BY level ASC, source ASC;
            """
            cur.execute(query, {
                'class_name': char_class,
                'subclass_name': subclass_name,
                'level': level
            })
            return cur.fetchall()


def get_spells_for_class(char_class: str, char_level: int, known_spells: Optional[List[str]] = None):
    if known_spells is None:
        known_spells = []

    prepared_casters = {'Жрец', 'Друид', 'Волшебник', 'Паладин', 'Изобретатель'}
    is_prepared = char_class in prepared_casters

    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT * 
                FROM spells 
                WHERE %s = ANY(classes)
                ORDER BY level ASC, name_ru ASC
            """, (char_class,))

            available_spells = cur.fetchall()

    known_spells_data = [s for s in available_spells if s['name_ru'] in known_spells]

    return available_spells, known_spells_data, is_prepared