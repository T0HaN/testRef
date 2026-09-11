from uuid import UUID
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from fastapi import APIRouter, Request, Depends, HTTPException, status, Query
from fastapi.responses import HTMLResponse, RedirectResponse
import psycopg2.extras

from dependencies import templates, get_current_user
from utils import get_db_connection

market_router = APIRouter(prefix="/market", tags=["Marketplace"])

PLATFORM_FEE_MULTIPLIER = Decimal("1.10")


def calc_market_price(author_price: Decimal) -> Decimal:
    """Цена на витрине с наценкой платформы x1.1"""
    return (Decimal(str(author_price)) * PLATFORM_FEE_MULTIPLIER).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# 1. Каталог паков (Витрина магазина)
@market_router.get("", response_class=HTMLResponse)
async def market_catalog(
        request: Request,
        q: Optional[str] = Query(None),
        license_type: Optional[str] = Query(None),
        current_user: dict = Depends(get_current_user)
):
    query = """
        SELECT p.*, u.username AS author_name, COUNT(pa.asset_id) AS assets_count
        FROM packs p
        JOIN users u ON p.author_id = u.id
        LEFT JOIN pack_assets pa ON p.id = pa.pack_id
        WHERE p.is_published = TRUE
    """
    params = []

    if q:
        query += " AND (p.title ILIKE %s OR p.description ILIKE %s)"
        params.extend([f"%{q.strip()}%", f"%{q.strip()}%"])

    if license_type in ['personal', 'commercial']:
        query += " AND p.license_type = %s"
        params.append(license_type)

    query += " GROUP BY p.id, u.username ORDER BY p.created_at DESC"

    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, params)
            packs = cur.fetchall()

            # Проверяем, какие паки уже куплены текущим пользователем
            cur.execute("SELECT pack_id FROM purchases WHERE buyer_id = %s", (current_user['id'],))
            owned_pack_ids = {str(row['pack_id']) for row in cur.fetchall()}

    for pack in packs:
        pack["market_price"] = calc_market_price(pack["price"])
        pack["is_owned"] = str(pack["id"]) in owned_pack_ids
        pack["is_author"] = pack["author_id"] == current_user['id']

    return templates.TemplateResponse(request, "market/catalog.html", context={
        "user": current_user,
        "packs": packs,
        "search_query": q or "",
        "selected_license": license_type or "all"
    })


# 2. Детальная карточка пака
@market_router.get("/pack/{pack_id}", response_class=HTMLResponse)
async def pack_details(pack_id: UUID, request: Request, current_user: dict = Depends(get_current_user)):
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Информация о паке
            cur.execute("""
                SELECT p.*, u.username AS author_name
                FROM packs p
                JOIN users u ON p.author_id = u.id
                WHERE p.id = %s
            """, (str(pack_id),))
            pack = cur.fetchone()

            if not pack:
                raise HTTPException(status_code=404, detail="Пак не найден")

            # Список ассетов внутри пака
            cur.execute("""
                SELECT a.id, a.asset_type, a.title, a.description, a.cover_image_url,
                       m.armor_class, m.hit_points, m.challenge_rating,
                       s.level AS spell_level, s.school AS spell_school,
                       mp.grid_width, mp.grid_height
                FROM pack_assets pa
                JOIN marketplace_assets a ON pa.asset_id = a.id
                LEFT JOIN custom_monsters m ON a.id = m.asset_id
                LEFT JOIN custom_spells s ON a.id = s.asset_id
                LEFT JOIN custom_maps mp ON a.id = mp.asset_id
                WHERE pa.pack_id = %s
                ORDER BY pa.sort_order ASC, a.title ASC
            """, (str(pack_id),))
            assets = cur.fetchall()

            # Проверка владения
            cur.execute("SELECT id FROM purchases WHERE buyer_id = %s AND pack_id = %s",
                        (current_user['id'], str(pack_id)))
            is_owned = cur.fetchone() is not None

    pack["market_price"] = calc_market_price(pack["price"])
    pack["is_owned"] = is_owned
    pack["is_author"] = pack["author_id"] == current_user['id']

    return templates.TemplateResponse(request, "market/pack_detail.html", context={
        "user": current_user,
        "pack": pack,
        "assets": assets
    })


# 3. Покупка пака
@market_router.post("/pack/{pack_id}/buy")
async def buy_pack(pack_id: UUID, current_user: dict = Depends(get_current_user)):
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # 1. Получаем пак
            cur.execute("SELECT * FROM packs WHERE id = %s AND is_published = TRUE", (str(pack_id),))
            pack = cur.fetchone()

            if not pack:
                raise HTTPException(status_code=404, detail="Пак не найден или снят с продажи")

            if pack["author_id"] == current_user['id']:
                raise HTTPException(status_code=400, detail="Нельзя купить собственный пак")

            # 2. Проверяем, не куплен ли он уже
            cur.execute("SELECT id FROM purchases WHERE buyer_id = %s AND pack_id = %s",
                        (current_user['id'], str(pack_id)))
            if cur.fetchone():
                return RedirectResponse(url=f"/market/pack/{pack_id}?info=already_owned", status_code=status.HTTP_303_SEE_OTHER)

            market_price = calc_market_price(pack["price"])
            author_payout = Decimal(str(pack["price"]))

            # 3. Фиксируем транзакцию покупки
            cur.execute("""
                INSERT INTO purchases (buyer_id, pack_id, price_paid, payment_method, status)
                VALUES (%s, %s, %s, 'balance', 'completed')
                RETURNING id
            """, (current_user['id'], str(pack_id), market_price))
            purchase_id = cur.fetchone()['id']

            # 4. Начисляем чистый доход автору (без комиссии платформы)
            cur.execute("""
                UPDATE users 
                SET total_earnings = COALESCE(total_earnings, 0) + %s 
                WHERE id = %s
            """, (author_payout, pack["author_id"]))

            # 5. Распаковываем все ассеты пака в личную библиотеку покупателя
            cur.execute("SELECT asset_id FROM pack_assets WHERE pack_id = %s", (str(pack_id),))
            pack_assets = cur.fetchall()

            for item in pack_assets:
                cur.execute("""
                    INSERT INTO user_library (user_id, asset_id, acquired_via, source_pack_id, purchase_id)
                    VALUES (%s, %s, 'purchase', %s, %s)
                    ON CONFLICT (user_id, asset_id) DO NOTHING
                """, (current_user['id'], str(item['asset_id']), str(pack_id), purchase_id))

            conn.commit()

    return RedirectResponse(url=f"/market/pack/{pack_id}?success=purchased", status_code=status.HTTP_303_SEE_OTHER)