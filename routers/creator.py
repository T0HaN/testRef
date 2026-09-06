import json
from uuid import UUID
from fastapi import APIRouter, Request, Form, File, UploadFile, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
import psycopg2.extras

from config import settings
from dependencies import templates, get_current_user
from utils import get_db_connection
from utils import get_db_connection, upload_asset_file

creator_router = APIRouter(prefix="/creator", tags=["Asset Creator"])


# 1. Список ассетов автора
@creator_router.get("/assets", response_class=HTMLResponse)
async def my_assets_page(request: Request, current_user: dict = Depends(get_current_user)):
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT id, asset_type, title, description, cover_image_url, price, 
                       license_type, is_published, created_at, updated_at
                FROM marketplace_assets
                WHERE author_id = %s
                ORDER BY updated_at DESC
            """, (current_user['id'],))
            assets = cur.fetchall()

    return templates.TemplateResponse(request, "creator/asset_list.html", context={
        "user": current_user,
        "assets": assets
    })


# 2. Страница создания ассета
@creator_router.get("/assets/new", response_class=HTMLResponse)
async def new_asset_page(request: Request, current_user: dict = Depends(get_current_user)):
    return templates.TemplateResponse(request, "creator/asset_form.html", context={
        "user": current_user,
        "asset": None,
        "is_edit": False
    })


# 3. Создание ассета (POST)
@creator_router.post("/assets/new")
async def create_asset(
        request: Request,
        title: str = Form(...),
        asset_type: str = Form(...),
        description: str = Form(""),
        price: float = Form(0.0),
        license_type: str = Form("personal"),
        is_published: bool = Form(False),
        metadata_json: str = Form("{}"),
        cover_image: UploadFile = File(None),
        content_file: UploadFile = File(None),
        current_user: dict = Depends(get_current_user)
):
    try:
        parsed_metadata = json.loads(metadata_json)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Некорректный формат метаданных")

    cover_url = None
    if cover_image and cover_image.filename:
        cover_bytes = await cover_image.read()
        cover_url = upload_asset_file(cover_bytes, cover_image.filename, cover_image.content_type, folder="covers")

    # Если для карты или музыки прикреплен файл медиа:
    if content_file and content_file.filename:
        content_bytes = await content_file.read()
        content_url = upload_asset_file(content_bytes, content_file.filename, content_file.content_type,
                                        folder="content")
        parsed_metadata["file_url"] = content_url

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # Делаем пользователя креатором, если он ещё им не был
            cur.execute("UPDATE users SET is_creator = TRUE WHERE id = %s AND is_creator = FALSE",
                        (current_user['id'],))

            cur.execute("""
                INSERT INTO marketplace_assets 
                (author_id, asset_type, title, description, cover_image_url, metadata, price, license_type, is_published)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                current_user['id'], asset_type, title.strip(), description.strip(),
                cover_url, json.dumps(parsed_metadata), price, license_type, is_published
            ))
            conn.commit()

    return RedirectResponse(url="/creator/assets?success=created", status_code=status.HTTP_303_SEE_OTHER)


# 4. Страница редактирования ассета
@creator_router.get("/assets/{asset_id}/edit", response_class=HTMLResponse)
async def edit_asset_page(asset_id: UUID, request: Request, current_user: dict = Depends(get_current_user)):
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM marketplace_assets 
                WHERE id = %s AND author_id = %s
            """, (str(asset_id), current_user['id']))
            asset = cur.fetchone()

    if not asset:
        raise HTTPException(status_code=404, detail="Ассет не найден или нет прав на редактирование")

    return templates.TemplateResponse(request, "creator/asset_form.html", context={
        "user": current_user,
        "asset": asset,
        "is_edit": True
    })


# 5. Сохранение изменений (POST)
@creator_router.post("/assets/{asset_id}/edit")
async def update_asset(
        asset_id: UUID,
        title: str = Form(...),
        description: str = Form(""),
        price: float = Form(0.0),
        license_type: str = Form("personal"),
        is_published: bool = Form(False),
        metadata_json: str = Form("{}"),
        cover_image: UploadFile = File(None),
        content_file: UploadFile = File(None),
        current_user: dict = Depends(get_current_user)
):
    try:
        parsed_metadata = json.loads(metadata_json)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Некорректные метаданные")

    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM marketplace_assets WHERE id = %s AND author_id = %s",
                        (str(asset_id), current_user['id']))
            existing = cur.fetchone()
            if not existing:
                raise HTTPException(status_code=404, detail="Ассет не найден")

            cover_url = existing["cover_image_url"]
            if cover_image and cover_image.filename:
                cover_bytes = await cover_image.read()
                cover_url = upload_asset_file(cover_bytes, cover_image.filename, cover_image.content_type,
                                              folder="covers")

            if content_file and content_file.filename:
                content_bytes = await content_file.read()
                content_url = upload_asset_file(content_bytes, content_file.filename, content_file.content_type,
                                                folder="content")
                parsed_metadata["file_url"] = content_url
            elif "file_url" in existing["metadata"]:
                parsed_metadata["file_url"] = existing["metadata"]["file_url"]

            cur.execute("""
                UPDATE marketplace_assets 
                SET title = %s, description = %s, cover_image_url = %s, metadata = %s,
                    price = %s, license_type = %s, is_published = %s, updated_at = NOW()
                WHERE id = %s AND author_id = %s
            """, (
                title.strip(), description.strip(), cover_url, json.dumps(parsed_metadata),
                price, license_type, is_published, str(asset_id), current_user['id']
            ))
            conn.commit()

    return RedirectResponse(url="/creator/assets?success=updated", status_code=status.HTTP_303_SEE_OTHER)


# 6. Удаление ассета
@creator_router.post("/assets/{asset_id}/delete")
async def delete_asset(asset_id: UUID, current_user: dict = Depends(get_current_user)):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM marketplace_assets WHERE id = %s AND author_id = %s",
                        (str(asset_id), current_user['id']))
            conn.commit()

    return RedirectResponse(url="/creator/assets?success=deleted", status_code=status.HTTP_303_SEE_OTHER)