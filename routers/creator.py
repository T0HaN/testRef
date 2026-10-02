import json
import math
from uuid import UUID
from typing import List, Optional
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Request, Form, File, UploadFile, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
import psycopg2.extras

from dependencies import templates, get_current_user
from utils import (
    ALLOWED_AUDIO_EXTS, ALLOWED_AUDIO_TYPES, ALLOWED_IMAGE_EXTS, ALLOWED_IMAGE_TYPES, DEFAULT_MAX_UPLOAD_SIZE,
    MAX_AUDIO_UPLOAD_SIZE, get_db_connection, read_upload_limited,
    upload_asset_file,
)

creator_router = APIRouter(prefix="/creator", tags=["Asset Creator"])

PLATFORM_FEE_MULTIPLIER = Decimal("1.10")
ALLOWED_ASSET_TYPES = {"map", "monster", "spell", "class", "music"}
ALLOWED_LICENSE_TYPES = {"personal", "commercial"}


def validate_asset_fields(title: str, asset_type: str, license_type: str) -> None:
    if not title.strip() or len(title.strip()) > 200:
        raise HTTPException(status_code=400, detail="Название должно содержать от 1 до 200 символов")
    if asset_type not in ALLOWED_ASSET_TYPES:
        raise HTTPException(status_code=400, detail="Некорректный тип ассета")
    if license_type not in ALLOWED_LICENSE_TYPES:
        raise HTTPException(status_code=400, detail="Некорректный тип лицензии")


def validate_pack_fields(title: str, author_price: float, discount_percentage: int, license_type: str) -> None:
    if not title.strip() or len(title.strip()) > 200:
        raise HTTPException(status_code=400, detail="Название должно содержать от 1 до 200 символов")
    if license_type not in ALLOWED_LICENSE_TYPES:
        raise HTTPException(status_code=400, detail="Некорректный тип лицензии")
    if not math.isfinite(author_price) or author_price < 0 or author_price > 1_000_000:
        raise HTTPException(status_code=400, detail="Цена должна быть от 0 до 1 000 000")
    if discount_percentage < 0 or discount_percentage > 100:
        raise HTTPException(status_code=400, detail="Скидка должна быть от 0 до 100%")


async def store_upload(file: UploadFile, folder: str, *, allow_audio: bool = False) -> str:
    allowed_types = ALLOWED_AUDIO_TYPES if allow_audio else ALLOWED_IMAGE_TYPES
    allowed_extensions = ALLOWED_AUDIO_EXTS if allow_audio else ALLOWED_IMAGE_EXTS
    max_size = MAX_AUDIO_UPLOAD_SIZE if allow_audio else DEFAULT_MAX_UPLOAD_SIZE
    try:
        content = await read_upload_limited(file, allowed_types, max_size, allowed_extensions)
        return upload_asset_file(content, file.filename or "upload", file.content_type or "", folder=folder)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def calc_market_price(author_price: Decimal) -> Decimal:
    """Вычисляет итоговую цену на витрине с наценкой x1.1 (округление до копеек)"""
    return (Decimal(str(author_price)) * PLATFORM_FEE_MULTIPLIER).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ============================================================
# === ЕДИНЫЙ ХАБ КУЗНИ (Вкладки: Паки и Ассеты) ===
# ============================================================

@creator_router.get("", response_class=HTMLResponse)
@creator_router.get("/", response_class=HTMLResponse)
async def creator_dashboard(
        request: Request,
        tab: str = "packs",
        current_user: dict = Depends(get_current_user)
):
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # 1. Загрузка паков автора
            cur.execute("""
                SELECT p.*, COUNT(pa.asset_id) AS assets_count
                FROM packs p
                LEFT JOIN pack_assets pa ON p.id = pa.pack_id
                WHERE p.author_id = %s
                GROUP BY p.id
                ORDER BY p.updated_at DESC
            """, (current_user['id'],))
            packs = cur.fetchall()

            for pack in packs:
                pack["market_price"] = calc_market_price(pack["price"])

            # 2. Загрузка строительных ассетов
            cur.execute("""
                SELECT id, asset_type, title, description, cover_image_url, 
                       license_type, created_at, updated_at
                FROM marketplace_assets
                WHERE author_id = %s
                ORDER BY updated_at DESC
            """, (current_user['id'],))
            assets = cur.fetchall()

    return templates.TemplateResponse(request, "creator/dashboard.html", context={
        "user": current_user,
        "packs": packs,
        "assets": assets,
        "active_tab": tab if tab in ["packs", "assets"] else "packs"
    })


# ============================================================
# === АССЕТЫ (Строительные блоки автора) ===
# ============================================================

@creator_router.get("/assets", response_class=HTMLResponse)
async def my_assets_page(request: Request, current_user: dict = Depends(get_current_user)):
    return RedirectResponse(url="/creator?tab=assets", status_code=status.HTTP_302_FOUND)


@creator_router.get("/assets/new", response_class=HTMLResponse)
async def new_asset_page(request: Request, current_user: dict = Depends(get_current_user)):
    return templates.TemplateResponse(request, "creator/asset_form.html", context={
        "user": current_user,
        "asset": None,
        "is_edit": False
    })


@creator_router.post("/assets/new")
async def create_asset(
        request: Request,
        title: str = Form(...),
        asset_type: str = Form(...),
        description: str = Form(""),
        license_type: str = Form("personal"),
        metadata_json: str = Form("{}"),
        cover_image: UploadFile = File(None),
        content_file: UploadFile = File(None),
        current_user: dict = Depends(get_current_user)
):
    validate_asset_fields(title, asset_type, license_type)
    if len(description) > 10_000 or len(metadata_json) > 100_000:
        raise HTTPException(status_code=400, detail="Слишком большой объём данных ассета")
    try:
        data = json.loads(metadata_json)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Некорректный JSON параметров")

    cover_url = None
    if cover_image and cover_image.filename:
        cover_url = await store_upload(cover_image, "covers")

    content_url = None
    if content_file and content_file.filename:
        content_url = await store_upload(content_file, "content", allow_audio=asset_type == "music")

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET is_creator = TRUE WHERE id = %s AND is_creator = FALSE", (current_user['id'],))

            cur.execute("""
                INSERT INTO marketplace_assets (author_id, asset_type, title, description, cover_image_url, license_type)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (current_user['id'], asset_type, title.strip(), description.strip(), cover_url, license_type))
            asset_id = cur.fetchone()[0]

            if asset_type == 'monster':
                attrs = data.get('attributes') or {"str": 10, "dex": 10, "con": 10, "int": 10, "wis": 10, "cha": 10}
                cur.execute("""
                    INSERT INTO custom_monsters 
                    (asset_id, meta, armor_class, hit_points, hit_dice, speed, challenge_rating, attributes, traits, actions, legendary_actions, token_url)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    asset_id, data.get('meta', ''), int(data.get('armor_class', 10) or 10), int(data.get('hit_points', 10) or 10),
                    data.get('hit_dice', '1d8'), data.get('speed', '30 фт.'), str(data.get('challenge_rating', '1')),
                    json.dumps(attrs), json.dumps(data.get('traits', [])), json.dumps(data.get('actions', [])),
                    json.dumps(data.get('legendary_actions', [])), content_url
                ))

            elif asset_type == 'spell':
                cur.execute("""
                    INSERT INTO custom_spells 
                    (asset_id, name_en, level, school, casting_time, range, components, duration, classes, source)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    asset_id, data.get('name_en', ''), int(data.get('level', 0) or 0), data.get('school', 'Воплощение'),
                    data.get('casting_time', '1 действие'), data.get('range', '60 футов'), data.get('components', 'В, С'),
                    data.get('duration', 'Мгновенная'), data.get('classes', []), data.get('source', 'Homebrew')
                ))

            elif asset_type == 'map':
                cur.execute("""
                    INSERT INTO custom_maps (asset_id, grid_width, grid_height, map_image_url)
                    VALUES (%s, %s, %s, %s)
                """, (asset_id, int(data.get('grid_width', 30) or 30), int(data.get('grid_height', 30) or 30), content_url or ''))

            elif asset_type == 'music':
                cur.execute("""
                    INSERT INTO custom_audio (asset_id, audio_url, tags, is_loop)
                    VALUES (%s, %s, %s, %s)
                """, (asset_id, content_url or '', data.get('tags', ''), bool(data.get('loop', True))))

            elif asset_type == 'class':
                cur.execute("""
                    INSERT INTO custom_classes (asset_id, hit_die, primary_stat)
                    VALUES (%s, %s, %s)
                """, (asset_id, data.get('hit_die', 'd8'), data.get('primary_stat', 'Сила')))

            conn.commit()

    return RedirectResponse(url="/creator?tab=assets&success=created", status_code=status.HTTP_303_SEE_OTHER)


@creator_router.get("/assets/{asset_id}/edit", response_class=HTMLResponse)
async def edit_asset_page(asset_id: UUID, request: Request, current_user: dict = Depends(get_current_user)):
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT a.*, 
                       m.meta, m.armor_class, m.hit_points, m.hit_dice, m.speed, m.challenge_rating, 
                       m.attributes, m.traits, m.actions, m.legendary_actions, m.token_url,
                       s.name_en, s.level, s.school, s.casting_time, s.range, s.components, s.duration, s.classes, s.source,
                       mp.grid_width, mp.grid_height, mp.map_image_url,
                       au.audio_url, au.tags, au.is_loop,
                       cl.hit_die, cl.primary_stat
                FROM marketplace_assets a
                LEFT JOIN custom_monsters m ON a.id = m.asset_id
                LEFT JOIN custom_spells s ON a.id = s.asset_id
                LEFT JOIN custom_maps mp ON a.id = mp.asset_id
                LEFT JOIN custom_audio au ON a.id = au.asset_id
                LEFT JOIN custom_classes cl ON a.id = cl.asset_id
                WHERE a.id = %s AND a.author_id = %s
            """, (str(asset_id), current_user['id']))
            row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Ассет не найден")

    metadata = {}
    atype = row['asset_type']
    if atype == 'monster':
        metadata = {
            'meta': row['meta'], 'armor_class': row['armor_class'], 'hit_points': row['hit_points'],
            'hit_dice': row['hit_dice'], 'speed': row['speed'], 'challenge_rating': row['challenge_rating'],
            'attributes': row['attributes'], 'traits': row['traits'], 'actions': row['actions'],
            'legendary_actions': row['legendary_actions'], 'file_url': row['token_url']
        }
    elif atype == 'spell':
        metadata = {
            'name_en': row['name_en'], 'level': row['level'], 'school': row['school'],
            'casting_time': row['casting_time'], 'range': row['range'], 'components': row['components'],
            'duration': row['duration'], 'classes': row['classes'], 'source': row['source']
        }
    elif atype == 'map':
        metadata = {'grid_width': row['grid_width'], 'grid_height': row['grid_height'], 'file_url': row['map_image_url']}
    elif atype == 'music':
        metadata = {'tags': row['tags'], 'loop': row['is_loop'], 'file_url': row['audio_url']}
    elif atype == 'class':
        metadata = {'hit_die': row['hit_die'], 'primary_stat': row['primary_stat']}

    row['metadata'] = metadata

    return templates.TemplateResponse(request, "creator/asset_form.html", context={
        "user": current_user,
        "asset": row,
        "is_edit": True
    })


@creator_router.post("/assets/{asset_id}/edit")
async def update_asset(
        asset_id: UUID,
        title: str = Form(...),
        description: str = Form(""),
        license_type: str = Form("personal"),
        metadata_json: str = Form("{}"),
        cover_image: UploadFile = File(None),
        content_file: UploadFile = File(None),
        current_user: dict = Depends(get_current_user)
):
    try:
        data = json.loads(metadata_json)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Некорректный JSON параметров")

    if not title.strip() or len(title.strip()) > 200:
        raise HTTPException(status_code=400, detail="Название должно содержать от 1 до 200 символов")
    if license_type not in ALLOWED_LICENSE_TYPES:
        raise HTTPException(status_code=400, detail="Некорректный тип лицензии")
    if len(description) > 10_000 or len(metadata_json) > 100_000:
        raise HTTPException(status_code=400, detail="Слишком большой объём данных ассета")

    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM marketplace_assets WHERE id = %s AND author_id = %s",
                        (str(asset_id), current_user['id']))
            existing = cur.fetchone()
            if not existing:
                raise HTTPException(status_code=404, detail="Ассет не найден")

            cover_url = existing["cover_image_url"]
            if cover_image and cover_image.filename:
                cover_url = await store_upload(cover_image, "covers")

            content_url = None
            if content_file and content_file.filename:
                content_url = await store_upload(
                    content_file, "content", allow_audio=existing['asset_type'] == "music"
                )

            cur.execute("""
                UPDATE marketplace_assets 
                SET title = %s, description = %s, cover_image_url = %s, license_type = %s, updated_at = NOW()
                WHERE id = %s AND author_id = %s
            """, (title.strip(), description.strip(), cover_url, license_type, str(asset_id), current_user['id']))

            atype = existing['asset_type']
            if atype == 'monster':
                cur.execute("""
                    UPDATE custom_monsters SET
                        meta = %s, armor_class = %s, hit_points = %s, hit_dice = %s, speed = %s,
                        challenge_rating = %s, attributes = %s, traits = %s, actions = %s,
                        legendary_actions = %s, token_url = COALESCE(%s, token_url)
                    WHERE asset_id = %s
                """, (
                    data.get('meta', ''), int(data.get('armor_class', 10) or 10), int(data.get('hit_points', 10) or 10),
                    data.get('hit_dice', '1d8'), data.get('speed', '30 фт.'), str(data.get('challenge_rating', '1')),
                    json.dumps(data.get('attributes') or {}), json.dumps(data.get('traits', [])),
                    json.dumps(data.get('actions', [])), json.dumps(data.get('legendary_actions', [])),
                    content_url, str(asset_id)
                ))

            elif atype == 'spell':
                cur.execute("""
                    UPDATE custom_spells SET
                        name_en = %s, level = %s, school = %s, casting_time = %s, range = %s,
                        components = %s, duration = %s, classes = %s, source = %s
                    WHERE asset_id = %s
                """, (
                    data.get('name_en', ''), int(data.get('level', 0) or 0), data.get('school', 'Воплощение'),
                    data.get('casting_time', '1 действие'), data.get('range', '60 футов'),
                    data.get('components', 'В, С'), data.get('duration', 'Мгновенная'),
                    data.get('classes', []), data.get('source', 'Homebrew'), str(asset_id)
                ))

            elif atype == 'map':
                cur.execute("""
                    UPDATE custom_maps SET
                        grid_width = %s, grid_height = %s, map_image_url = COALESCE(%s, map_image_url)
                    WHERE asset_id = %s
                """, (int(data.get('grid_width', 30) or 30), int(data.get('grid_height', 30) or 30), content_url, str(asset_id)))

            elif atype == 'music':
                cur.execute("""
                    UPDATE custom_audio SET
                        tags = %s, is_loop = %s, audio_url = COALESCE(%s, audio_url)
                    WHERE asset_id = %s
                """, (data.get('tags', ''), bool(data.get('loop', True)), content_url, str(asset_id)))

            elif atype == 'class':
                cur.execute("""
                    UPDATE custom_classes SET hit_die = %s, primary_stat = %s WHERE asset_id = %s
                """, (data.get('hit_die', 'd8'), data.get('primary_stat', 'Сила'), str(asset_id)))

            conn.commit()

    return RedirectResponse(url="/creator?tab=assets&success=updated", status_code=status.HTTP_303_SEE_OTHER)


@creator_router.post("/assets/{asset_id}/delete")
async def delete_asset(asset_id: UUID, current_user: dict = Depends(get_current_user)):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM marketplace_assets WHERE id = %s AND author_id = %s",
                        (str(asset_id), current_user['id']))
            conn.commit()

    return RedirectResponse(url="/creator?tab=assets&success=deleted", status_code=status.HTTP_303_SEE_OTHER)


# ============================================================
# === ПАКИ (Товары маркетплейса) ===
# ============================================================

@creator_router.get("/packs", response_class=HTMLResponse)
async def my_packs_page(request: Request, current_user: dict = Depends(get_current_user)):
    return RedirectResponse(url="/creator?tab=packs", status_code=status.HTTP_302_FOUND)


@creator_router.get("/packs/new", response_class=HTMLResponse)
async def new_pack_page(request: Request, current_user: dict = Depends(get_current_user)):
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT id, asset_type, title, cover_image_url 
                FROM marketplace_assets 
                WHERE author_id = %s 
                ORDER BY asset_type, title
            """, (current_user['id'],))
            user_assets = cur.fetchall()

    return templates.TemplateResponse(request, "creator/pack_form.html", context={
        "user": current_user,
        "pack": None,
        "user_assets": user_assets,
        "selected_asset_ids": [],
        "is_edit": False
    })


@creator_router.post("/packs/new")
async def create_pack(
        request: Request,
        title: str = Form(...),
        description: str = Form(""),
        author_price: float = Form(0.0),
        discount_percentage: int = Form(0),
        license_type: str = Form("personal"),
        is_published: bool = Form(False),
        asset_ids: List[UUID] = Form([]),
        cover_image: UploadFile = File(None),
        current_user: dict = Depends(get_current_user)
):
    validate_pack_fields(title, author_price, discount_percentage, license_type)
    if len(description) > 10_000:
        raise HTTPException(status_code=400, detail="Описание слишком длинное")
    if not asset_ids:
        raise HTTPException(status_code=400, detail="Пак должен содержать хотя бы один ассет")

    target_asset_ids = [str(aid) for aid in asset_ids]

    cover_url = None
    if cover_image and cover_image.filename:
        cover_url = await store_upload(cover_image, "pack_covers")

    author_price_dec = Decimal(str(max(0.0, author_price)))

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # Безопасная проверка: передаем кортеж строк в IN %s
            cur.execute("""
                SELECT id::text FROM marketplace_assets 
                WHERE author_id = %s AND id::text IN %s
            """, (current_user['id'], tuple(target_asset_ids)))
            valid_ids = [row[0] for row in cur.fetchall()]

            if len(valid_ids) != len(target_asset_ids):
                raise HTTPException(status_code=403, detail="Выбран чужой или несуществующий ассет")

            cur.execute("""
                INSERT INTO packs 
                (author_id, title, description, cover_image_url, price, license_type, discount_percentage, is_published)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (current_user['id'], title.strip(), description.strip(), cover_url,
                  author_price_dec, license_type, discount_percentage, is_published))
            pack_id = cur.fetchone()[0]

            for order, aid in enumerate(target_asset_ids):
                cur.execute("""
                    INSERT INTO pack_assets (pack_id, asset_id, sort_order)
                    VALUES (%s, %s, %s)
                """, (pack_id, aid, order))

            conn.commit()

    return RedirectResponse(url="/creator?tab=packs&success=created", status_code=status.HTTP_303_SEE_OTHER)


@creator_router.get("/packs/{pack_id}/edit", response_class=HTMLResponse)
async def edit_pack_page(pack_id: UUID, request: Request, current_user: dict = Depends(get_current_user)):
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM packs WHERE id = %s AND author_id = %s", (str(pack_id), current_user['id']))
            pack = cur.fetchone()
            if not pack:
                raise HTTPException(status_code=404, detail="Пак не найден")

            cur.execute("""
                SELECT id, asset_type, title, cover_image_url 
                FROM marketplace_assets 
                WHERE author_id = %s 
                ORDER BY asset_type, title
            """, (current_user['id'],))
            user_assets = cur.fetchall()

            cur.execute("SELECT asset_id FROM pack_assets WHERE pack_id = %s", (str(pack_id),))
            selected_asset_ids = [str(row["asset_id"]) for row in cur.fetchall()]

    return templates.TemplateResponse(request, "creator/pack_form.html", context={
        "user": current_user,
        "pack": pack,
        "user_assets": user_assets,
        "selected_asset_ids": selected_asset_ids,
        "is_edit": True
    })


@creator_router.post("/packs/{pack_id}/edit")
async def update_pack(
        pack_id: UUID,
        title: str = Form(...),
        description: str = Form(""),
        author_price: float = Form(0.0),
        discount_percentage: int = Form(0),
        license_type: str = Form("personal"),
        is_published: bool = Form(False),
        asset_ids: List[UUID] = Form([]),
        cover_image: UploadFile = File(None),
        current_user: dict = Depends(get_current_user)
):
    validate_pack_fields(title, author_price, discount_percentage, license_type)
    if len(description) > 10_000:
        raise HTTPException(status_code=400, detail="Описание слишком длинное")
    if not asset_ids:
        raise HTTPException(status_code=400, detail="В паке должен быть хотя бы один ассет")

    target_asset_ids = [str(aid) for aid in asset_ids]
    author_price_dec = Decimal(str(max(0.0, author_price)))

    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM packs WHERE id = %s AND author_id = %s", (str(pack_id), current_user['id']))
            existing = cur.fetchone()
            if not existing:
                raise HTTPException(status_code=404, detail="Пак не найден")

            # Безопасная проверка: передаем кортеж строк в IN %s
            cur.execute("""
                SELECT id::text FROM marketplace_assets 
                WHERE author_id = %s AND id::text IN %s
            """, (current_user['id'], tuple(target_asset_ids)))
            valid_ids = [row['id'] for row in cur.fetchall()]

            if len(valid_ids) != len(target_asset_ids):
                raise HTTPException(status_code=403, detail="Выбран чужой или несуществующий ассет")

            cover_url = existing["cover_image_url"]
            if cover_image and cover_image.filename:
                cover_url = await store_upload(cover_image, "pack_covers")

            cur.execute("""
                UPDATE packs 
                SET title = %s, description = %s, cover_image_url = %s, price = %s,
                    license_type = %s, discount_percentage = %s, is_published = %s, updated_at = NOW()
                WHERE id = %s AND author_id = %s
            """, (title.strip(), description.strip(), cover_url, author_price_dec,
                  license_type, discount_percentage, is_published, str(pack_id), current_user['id']))

            cur.execute("DELETE FROM pack_assets WHERE pack_id = %s", (str(pack_id),))
            for order, aid in enumerate(target_asset_ids):
                cur.execute("""
                    INSERT INTO pack_assets (pack_id, asset_id, sort_order)
                    VALUES (%s, %s, %s)
                """, (str(pack_id), aid, order))

            conn.commit()

    return RedirectResponse(url="/creator?tab=packs&success=updated", status_code=status.HTTP_303_SEE_OTHER)


@creator_router.post("/packs/{pack_id}/delete")
async def delete_pack(pack_id: UUID, current_user: dict = Depends(get_current_user)):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM packs WHERE id = %s AND author_id = %s", (str(pack_id), current_user['id']))
            conn.commit()

    return RedirectResponse(url="/creator?tab=packs&success=deleted", status_code=status.HTTP_303_SEE_OTHER)
