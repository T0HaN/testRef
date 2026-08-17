import base64
import traceback
import uuid
from typing import Optional

from fastapi import APIRouter, Request, Depends, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

import utils
from models import TokenUpload
from dependencies import require_player, get_current_user, check_character_ownership, templates
from utils import (
    load_chars, save_chars, normalize_char, calculate_ac,
    prepare_skills_and_saves, get_class_features, get_level_progress,
    calc_level_from_xp, calc_modifier, calc_prof_bonus,
    CLASSES_DATA, EQUIPMENT_DATA, XP_THRESHOLDS,
    parse_damage, map_weapon_type, determine_weapon_proficiency, get_all_spells, get_random_quote, load_equipment,
    upload_image_to_s3  # 🆕 Импорт функции для S3
)
from routers.websockets import broadcast_ws_event

router = APIRouter(tags=["Characters"])

# ============================================================
# === КОНСТАНТЫ (Вынесены, чтобы избежать дублирования) ===
# ============================================================

DND_RACES = [
    "Ааракокра", "Аасимар", "Автогном", "Астральный эльф", "Багбир",
    "Ведьмовская кровь", "Ведалкен", "Вердан", "Возрождённый", "Гибрид Симиков",
    "Гитцерай", "Гитъянки", "Гифф", "Гном", "Гоблин", "Голиаф", "Грунг",
    "Дампир", "Дварф", "Дженази", "Драконорожденный", "Дуэргар", "Зайцегон",
    "Калаштар", "Кендер", "Кенку", "Кентавр", "Кобольд", "Кованый", "Леонин",
    "Локата", "Локсодон", "Людоящер", "Минотавр", "Орк", "Полуорк", "Полурослик",
    "Полуэльф", "Сатир", "Совлин", "Табакси", "Тифлинг", "Тортл", "Три-крин",
    "Тритон", "Фирболг", "Фэйри", "Хадози", "Хобгоблин", "Хобгоблин из Страны Фей",
    "Чейнджлинг", "Человек", "Шадар-кай", "Шифтер", "Эладрин", "Эльф", "Юань-ти"
]

DND_CLASSES = [
    "Воин", "Волшебник", "Плут", "Жрец", "Бард", "Следопыт", "Паладин",
    "Варвар", "Друид", "Монах", "Чародей", "Колдун", "Изобретатель"
]

DND_ALIGNMENTS = [
    "Законопослушный добрый", "Нейтральный добрый", "Хаотичный добрый",
    "Законопослушный нейтральный", "Истинно нейтральный", "Хаотичный нейтральный",
    "Законопослушный злой", "Нейтральный злой", "Хаотичный злой"
]

DND_STATS = ["STR", "DEX", "CON", "INT", "WIS", "CHA"]

DND_STATS_RU = {
    "STR": "Сила", "DEX": "Ловкость", "CON": "Телосложение",
    "INT": "Интеллект", "WIS": "Мудрость", "CHA": "Харизма"
}

DND_SKILLS = [
    ("athletics", "Атлетика", "STR"), ("acrobatics", "Акробатика", "DEX"),
    ("sleight_of_hand", "Ловкость рук", "DEX"), ("stealth", "Скрытность", "DEX"),
    ("arcana", "Магия", "INT"), ("history", "История", "INT"),
    ("investigation", "Расследование", "INT"), ("religion", "Религия", "INT"),
    ("nature", "Природа", "INT"), ("animal_handling", "Уход за животными", "WIS"),
    ("insight", "Проницательность", "WIS"), ("medicine", "Медицина", "WIS"),
    ("perception", "Внимательность", "WIS"), ("survival", "Выживание", "WIS"),
    ("deception", "Обман", "CHA"), ("intimidation", "Запугивание", "CHA"),
    ("performance", "Выступление", "CHA"), ("persuasion", "Убеждение", "CHA"),
]

DND_SAVES = [
    ("str_save", "Сила"), ("dex_save", "Ловкость"), ("con_save", "Телосложение"),
    ("int_save", "Интеллект"), ("wis_save", "Мудрость"), ("cha_save", "Харизма"),
]


# ============================================================
# === Вспомогательные функции и роуты ===
# ============================================================

def _render_char_form_error(request: Request, error_msg: str, form_data=None):
    """Вспомогательная функция: возврат формы создания персонажа с ошибкой"""
    return templates.TemplateResponse(request, "char_form.html", context={
        "races": DND_RACES,
        "classes": DND_CLASSES,
        "subclasses": {cls: [] for cls in DND_CLASSES},
        "alignments": DND_ALIGNMENTS,
        "stats": DND_STATS,
        "stats_ru": DND_STATS_RU,
        "skills": DND_SKILLS,
        "saving_throws": DND_SAVES,
        "error": error_msg,
        "success": None,
        "info": None,
        "prefill": dict(form_data) if form_data is not None else None,
    })


@router.get("/chars", response_class=HTMLResponse)
async def chars_list(request: Request, current_user: dict = Depends(require_player)):
    chars = load_chars(current_user['username'])
    quote_text = get_random_quote()

    return templates.TemplateResponse(request, "CharList1.html", context={
        "chars": chars,
        "username": current_user['username'],
        "role": current_user.get('role', 'player'),
        "quote_text": quote_text,
        "error": None,
        "success": None,
        "info": None
    })


@router.get("/new_char", response_class=HTMLResponse)
async def new_char_form(request: Request, current_user: dict = Depends(require_player)):
    subclasses_map = {
        cls_name: [s.get('name', '').strip() for s in cls_data.get('subclasses', [])]
        for cls_name, cls_data in CLASSES_DATA.items()
    }

    return templates.TemplateResponse(request, "char_form.html", context={
        "races": DND_RACES,
        "classes": DND_CLASSES,
        "subclasses": subclasses_map,
        "alignments": DND_ALIGNMENTS,
        "stats": DND_STATS,
        "stats_ru": DND_STATS_RU,
        "skills": DND_SKILLS,
        "saving_throws": DND_SAVES,
        "username": current_user['username'],
        "error": None,
        "success": None,
        "info": None
    })


@router.post("/new_char")
async def create_character(request: Request, current_user: dict = Depends(require_player)):
    form = await request.form()

    try:
        name = form.get('name', '').strip()
        race = form.get('race', '')
        char_class = form.get('char_class', '')
        subclass = form.get('subclass', 'Нет')
        alignment = form.get('alignment', 'Истинно нейтральный')

        try:
            xp = int(form.get('xp') or 0)
        except (ValueError, TypeError):
            xp = 0

        level = calc_level_from_xp(xp)

        physical = {
            'height': form.get('height', ''),
            'weight': form.get('weight', ''),
            'hair': form.get('hair', ''),
            'eyes': form.get('eyes', '')
        }

        stats = {}
        for stat_key in DND_STATS:
            try:
                score = int(form.get(stat_key) or 10)
                score = max(1, min(30, score))
            except (ValueError, TypeError):
                score = 10
            stats[stat_key] = {
                'score': score,
                'modifier': calc_modifier(score)
            }

        saving_throws = form.getlist('saving_throws')
        skills = form.getlist('skills')

        ac = form.get('ac', '10')
        speed = form.get('speed', '30 фт')

        dex_mod = stats['DEX']['modifier']
        initiative = f"+{dex_mod}" if dex_mod >= 0 else str(dex_mod)

        try:
            hp_current = int(form.get('hp_current') or 10)
        except (ValueError, TypeError):
            hp_current = 10

        try:
            hp_max = int(form.get('hp_max') or 10)
        except (ValueError, TypeError):
            hp_max = 10

        try:
            hp_temp = int(form.get('hp_temp') or 0)
        except (ValueError, TypeError):
            hp_temp = 0

        if not name:
            return _render_char_form_error(request, "Имя персонажа обязательно", form_data=form)
        if not race:
            return _render_char_form_error(request, "Выберите расу", form_data=form)
        if not char_class:
            return _render_char_form_error(request, "Выберите класс", form_data=form)

        chars = load_chars(current_user['username'])

        new_char = {
            'name': name,
            'race': race,
            'char_class': char_class,
            'subclass': subclass,
            'alignment': alignment,
            'level': level,
            'xp': xp,
            'physical': physical,
            'stats': stats,
            'saving_throws': saving_throws,
            'skills': skills,
            'attributes': {
                'ac': ac,
                'initiative': initiative,
                'speed': speed,
                'prof_bonus': '+2'
            },
            'hp': {
                'current': hp_current,
                'max': hp_max,
                'temp': hp_temp
            },
            'description': '',
            'inventory': {
                'weapons': [], 'armor': [], 'gear': [],
                'arrows': [], 'bolts': [],
                'coins': {'cp': 0, 'sp': 0, 'ep': 0, 'gp': 0, 'pp': 0},
                'known_spells': []
            },
            'features_spells': ''
        }

        chars.append(new_char)
        save_chars(current_user['username'], chars)

        return RedirectResponse(url="/chars", status_code=303)

    except Exception as e:
        print(f"⚠️ Ошибка создания персонажа: {e}")
        traceback.print_exc()
        return _render_char_form_error(request, f"Ошибка: {str(e)}", form_data=form)


@router.get("/char/{char_id}", response_class=HTMLResponse)
async def view_char(char_id: int, request: Request, current_user: dict = Depends(require_player)):
    char = check_character_ownership(char_id, current_user['username'])

    char = normalize_char(char)
    char['_calculated_ac'] = calculate_ac(char)

    saves, skills = prepare_skills_and_saves(char)
    features = get_class_features(char.get('char_class', ''), char.get('subclass', 'Нет'), char.get('level', 1))

    current_level = char.get('level', 1)
    current_xp = char.get('xp', 0)
    xp_progress = get_level_progress(current_xp, current_level)
    next_level_xp = XP_THRESHOLDS[current_level] if current_level < 20 else "MAX"

    return templates.TemplateResponse(request, "character_view.html", context={
        "char": char,
        "saves": saves,
        "skills": skills,
        "class_features": features,
        "back_url": "/chars",
        "back_text": "← Назад к списку",
        "current_user": current_user,
        "xp_progress": xp_progress,
        "next_level_xp": next_level_xp,
        "error": None,
        "success": None
    })


@router.get("/char/{char_id}/edit", response_class=HTMLResponse)
async def edit_char_page(char_id: int, request: Request, current_user: dict = Depends(require_player)):
    char = check_character_ownership(char_id, current_user['username'])
    char = normalize_char(char)

    return templates.TemplateResponse(request, "edit_char.html", context={
        "char": char,
        "classes": list(CLASSES_DATA.keys()),
        "races": DND_RACES,
        "alignments": DND_ALIGNMENTS,
        "skills": DND_SKILLS,
        "saving_throws": DND_SAVES,
        "error": None,
        "success": None
    })


@router.post("/char/{char_id}/edit")
async def save_char_edit(char_id: int, request: Request, current_user: dict = Depends(require_player)):
    check_character_ownership(char_id, current_user['username'])
    form = await request.form()

    chars = load_chars(current_user['username'])
    char = next((c for c in chars if c['id'] == char_id), None)
    if not char:
        raise HTTPException(status_code=404, detail="Персонаж не найден")

    try:
        char['name'] = form.get('name', '').strip() or char['name']
        char['race'] = form.get('race', '').strip() or 'Человек'
        char['char_class'] = form.get('char_class', '').strip() or 'Воин'
        char['subclass'] = form.get('subclass', '').strip() or 'Нет'
        char['alignment'] = form.get('alignment', '').strip() or 'Истинно нейтральный'

        try:
            char['level'] = max(1, min(20, int(form.get('level', 1))))
        except (ValueError, TypeError):
            char['level'] = 1

        try:
            char['xp'] = max(0, int(form.get('xp', 0)))
        except (ValueError, TypeError):
            char['xp'] = 0

        for stat_key in DND_STATS:
            try:
                score = max(1, min(30, int(form.get(f'stat_{stat_key}', 10))))
                char['stats'][stat_key] = {
                    'score': score,
                    'modifier': calc_modifier(score)
                }
            except (ValueError, TypeError):
                pass

        char.setdefault('physical', {})
        char['physical']['height'] = form.get('height', '').strip()
        char['physical']['weight'] = form.get('weight', '').strip()
        char['physical']['hair'] = form.get('hair', '').strip()
        char['physical']['eyes'] = form.get('eyes', '').strip()

        try:
            char['hp']['current'] = max(0, int(form.get('hp_current', char['hp']['current'])))
            char['hp']['max'] = max(1, int(form.get('hp_max', char['hp']['max'])))
            char['hp']['temp'] = max(0, int(form.get('hp_temp', 0)))
        except (ValueError, TypeError):
            pass

        char.setdefault('attributes', {})
        char['attributes']['prof_bonus'] = f"+{calc_prof_bonus(char['level'])}"

        try:
            char['attributes']['speed'] = int(form.get('speed', char['attributes'].get('speed', 30)))
        except (ValueError, TypeError):
            pass

        char['attributes']['initiative'] = char['stats']['DEX']['modifier']

        char['skills'] = form.getlist('skills')
        char['saving_throws'] = form.getlist('saving_throws')

        save_chars(current_user['username'], chars)

        return RedirectResponse(
            url=f"/char/{char_id}?success=Персонаж обновлён",
            status_code=303
        )

    except Exception as e:
        return templates.TemplateResponse(request, "edit_char.html", context={
            "char": normalize_char(char),
            "classes": list(CLASSES_DATA.keys()),
            "races": DND_RACES,
            "alignments": DND_ALIGNMENTS,
            "skills": DND_SKILLS,
            "saving_throws": DND_SAVES,
            "error": f"Ошибка сохранения: {str(e)}",
            "success": None
        })


@router.post("/char/{char_id}/hp")
async def update_hp(
        char_id: int,
        username: str = Form(...),
        current_hp: int = Form(...),
        temp_hp: int = Form(0),
        room_id: Optional[str] = Form(None),
        current_user: dict = Depends(get_current_user)
):
    """Обновление текущего и временного здоровья персонажа"""
    if current_user['role'] == 'player':
        check_character_ownership(char_id, current_user['username'])

    user_chars = load_chars(username)
    char = next((c for c in user_chars if c['id'] == char_id), None)
    if not char:
        raise HTTPException(status_code=404, detail="Персонаж не найден")

    char.setdefault('hp', {'current': 10, 'max': 10, 'temp': 0})
    char['hp']['current'] = max(0, current_hp)
    char['hp']['temp'] = max(0, temp_hp)

    save_chars(username, user_chars)

    if room_id:
        try:
            room_id_int = int(room_id)
            await broadcast_ws_event(str(room_id_int), {
                'type': 'hp_update',
                'char_id': char_id,
                'username': username,
                'hp_current': char['hp']['current'],
                'hp_temp': char['hp']['temp'],
                'hp_max': char['hp']['max'],
                'updated_by': current_user['username']
            })
        except Exception as e:
            print(f"⚠️ Ошибка отправки HP_UPDATE: {e}")

    return {
        "status": "ok",
        "current_hp": char['hp']['current'],
        "temp_hp": char['hp']['temp'],
        "max_hp": char['hp']['max']
    }


@router.post("/char/{char_id}/token/upload")
async def upload_token(char_id: int, token_data: TokenUpload, current_user: dict = Depends(require_player)):
    check_character_ownership(char_id, current_user['username'])

    chars = load_chars(current_user['username'])
    char = next((c for c in chars if c['id'] == char_id), None)

    if not char:
        return {"status": "error", "error": "Персонаж не найден"}

    if len(token_data.image) > 3 * 1024 * 1024:
        return {"status": "error", "error": "Изображение слишком большое"}

    # 🆕 Если фронтенд прислал Base64, перехватываем и грузим в S3
    if token_data.image.startswith('data:image'):
        try:
            header, encoded = token_data.image.split(",", 1)
            content_type = header.split(":")[1].split(";")[0]
            extension = content_type.split("/")[1]

            # Защита от странных расширений
            if extension not in ['png', 'jpg', 'jpeg', 'webp', 'gif']:
                extension = 'png'

            image_bytes = base64.b64decode(encoded)
            file_name = f"tokens/char_{char_id}_{uuid.uuid4().hex[:8]}.{extension}"

            # Загружаем напрямую через встроенный клиент boto3
            utils.s3_client.put_object(
                Bucket=utils.settings.S3_BUCKET,
                Key=file_name,
                Body=image_bytes,
                ContentType=content_type
            )

            # Сохраняем в лист только красивую ссылку на S3
            char['token_image'] = f"/media/{file_name}"
        except Exception as e:
            print(f"Ошибка загрузки токена в S3: {e}")
            return {"status": "error", "error": "Не удалось загрузить изображение в хранилище"}
    else:
        # Если это уже URL (например, переиспользование), просто сохраняем
        char['token_image'] = token_data.image

    save_chars(current_user['username'], chars)
    return {"status": "ok", "message": "Токен загружен"}


@router.post("/char/{char_id}/token/remove")
async def remove_token(char_id: int, current_user: dict = Depends(require_player)):
    check_character_ownership(char_id, current_user['username'])

    chars = load_chars(current_user['username'])
    char = next((c for c in chars if c['id'] == char_id), None)

    if char:
        char['token_image'] = None
        save_chars(current_user['username'], chars)

    return RedirectResponse(url=f"/char/{char_id}", status_code=303)


@router.get("/char/{char_id}/description", response_class=HTMLResponse)
async def view_description(char_id: int, request: Request, current_user: dict = Depends(require_player)):
    char = check_character_ownership(char_id, current_user['username'])
    char = normalize_char(char)

    return templates.TemplateResponse(request, "char_description.html", context={
        "char": char,
        "error": None,
        "success": None
    })


@router.post("/char/{char_id}/description")
async def save_description(
        char_id: int,
        request: Request,
        char_image: Optional[UploadFile] = File(None),
        remove_image: Optional[str] = Form(None),
        appearance: str = Form(""),
        background: str = Form(""),
        allies: str = Form(""),
        personality: str = Form(""),
        ideals: str = Form(""),
        bonds: str = Form(""),
        flaws: str = Form(""),
        current_user: dict = Depends(require_player)
):
    check_character_ownership(char_id, current_user['username'])

    chars = load_chars(current_user['username'])
    char = next((c for c in chars if c['id'] == char_id), None)
    if not char:
        raise HTTPException(status_code=404, detail="Персонаж не найден")

    try:
        char['description_appearance'] = appearance.strip()
        char['description_background'] = background.strip()
        char['description_allies'] = allies.strip()
        char['description_personality'] = personality.strip()
        char['description_ideals'] = ideals.strip()
        char['description_bonds'] = bonds.strip()
        char['description_flaws'] = flaws.strip()

        if remove_image == "1":
            char['description_image'] = None
        elif char_image and char_image.filename:
            content = await char_image.read()

            if len(content) > 5 * 1024 * 1024:
                return templates.TemplateResponse(request, "char_description.html", context={
                    "char": char,
                    "error": "Файл слишком большой! Максимум 5MB.",
                    "success": None
                })

            if char_image.content_type not in ['image/jpeg', 'image/png', 'image/gif', 'image/webp']:
                return templates.TemplateResponse(request, "char_description.html", context={
                    "char": char,
                    "error": "Неподдерживаемый формат изображения.",
                    "success": None
                })

            # 🆕 Возвращаем указатель в начало файла после чтения размера
            await char_image.seek(0)

            # Используем готовую функцию загрузки в S3 (как в мастере)
            image_url = await upload_image_to_s3(char_image, prefix=f"portrait_char_{char_id}")
            char['description_image'] = image_url

        save_chars(current_user['username'], chars)
    except Exception as e:
        print(f"❌ Ошибка сохранения: {e}")
        traceback.print_exc()
        return templates.TemplateResponse(request, "char_description.html", context={
            "char": char,
            "error": f"Ошибка сохранения: {str(e)}",
            "success": None
        })

    return RedirectResponse(url=f"/char/{char_id}/description", status_code=303)


# ============================================================
# === ИНВЕНТАРЬ (ЗДЕСЬ БЫЛИ ИСПРАВЛЕНЫ БАГИ) ===
# ============================================================

@router.get("/char/{char_id}/inventory", response_class=HTMLResponse)
async def view_inventory(
        char_id: int,
        request: Request,
        current_user: dict = Depends(require_player)
):
    check_character_ownership(char_id, current_user['username'])
    chars = load_chars(current_user['username'])

    char = next((c for c in chars if c['id'] == char_id), None)
    if not char:
        return RedirectResponse(url="/chars", status_code=303)

    char = normalize_char(char)
    char['_calculated_ac'] = calculate_ac(char)

    db_equipment = utils.EQUIPMENT_DATA
    equip_catalog = {
        'weapons': db_equipment.get('weapons', {}),
        'armor': db_equipment.get('armor', {}),
        'gear': db_equipment.get('gear', [])
    }
    print(equip_catalog)

    return templates.TemplateResponse(request, "inventory.html", context={
        "char": char,
        "equipment": equip_catalog,
        "error": None,
        "success": None
    })


@router.post("/char/{char_id}/armor/toggle/{idx}")
async def toggle_armor(
        char_id: int,
        idx: int,
        request: Request,
        current_user: dict = Depends(require_player)
):
    check_character_ownership(char_id, current_user['username'])
    chars = load_chars(current_user['username'])
    char = next((c for c in chars if c['id'] == char_id), None)

    if not char:
        raise HTTPException(status_code=404, detail="Персонаж не найден")

    if 0 <= idx < len(char['inventory']['armor']):
        target_item = char['inventory']['armor'][idx]
        is_shield = 'ac_bonus' in target_item or target_item.get('name') == 'Щит'

        # Проверяем текущее состояние: надето или нет
        currently_equipped = target_item.get('equipped', False)

        if not currently_equipped:
            # Снимаем броню/щит того же типа перед надеванием новой
            for a in char['inventory']['armor']:
                item_is_shield = 'ac_bonus' in a or a.get('name') == 'Щит'
                if item_is_shield == is_shield:
                    a['equipped'] = False
            target_item['equipped'] = True
        else:
            # Если уже надето - просто снимаем
            target_item['equipped'] = False

        save_chars(current_user['username'], chars)

        # Пересчитываем AC, чтобы отдать его на фронт
        char['_calculated_ac'] = calculate_ac(char)

        # МАГИЯ: Определяем, это JS запрос (Fetch) или обычная HTML-форма
        # JS fetch обычно принимает application/json
        if "application/json" in request.headers.get("accept", ""):
            return {
                "status": "ok",
                "equipped": target_item['equipped'],
                "new_ac": char['_calculated_ac']
            }

    # Если это обычная форма, просто редиректим обратно в инвентарь
    return RedirectResponse(url=f"/char/{char_id}/inventory", status_code=303)


@router.post("/char/{char_id}/equipment/buy")
async def buy_equipment(char_id: int, request: Request, current_user: dict = Depends(require_player)):
    check_character_ownership(char_id, current_user['username'])
    form = await request.form()

    chars = load_chars(current_user['username'])
    char = next((c for c in chars if c['id'] == char_id), None)
    if not char:
        return RedirectResponse(url="/chars", status_code=303)

    char = normalize_char(char)
    item_name = form.get('item_name', '').strip()
    cost_str = form.get('cost', '0 зм')
    eq_type = form.get('eq_type', 'gear')

    if not item_name:
        return RedirectResponse(url=f"/char/{char_id}/inventory", status_code=303)

    try:
        if eq_type == 'weapon':
            found_item = None
            weapon_category = ''
            for cat_name, items in utils.EQUIPMENT_DATA.get('weapons', {}).items():
                for item in items:
                    if item.get('name') == item_name:
                        found_item = item
                        weapon_category = cat_name
                        break
                if found_item:
                    break

            if found_item:
                dmg = parse_damage(found_item.get('damage', '1d4'))
                w_type = map_weapon_type(found_item.get('properties', []))
                char_class = char.get('char_class', '')
                is_proficient = determine_weapon_proficiency(char_class, weapon_category, item_name)

                ammo_type = None
                if w_type == 'ammunition':
                    name_lower = item_name.lower()
                    if 'арбалет' in name_lower:
                        ammo_type = 'bolts'
                    elif 'лук' in name_lower or 'праща' in name_lower:
                        ammo_type = 'arrows'
                    else:
                        ammo_type = 'arrows'

                char['inventory']['weapons'].append({
                    'name': found_item['name'],
                    'type': w_type,
                    'damage': dmg,
                    'ammo_type': ammo_type,
                    'description': ', '.join(found_item.get('properties', [])),
                    'proficient': is_proficient,
                    'cost': found_item.get('cost'),
                    'weight': found_item.get('weight')
                })
            else:
                char['inventory']['weapons'].append({
                    'name': item_name,
                    'type': 'standard',
                    'damage': '1d4',
                    'description': '',
                    'proficient': True,
                    'cost': cost_str
                })



        elif eq_type == 'armor':

            found_item = None

            for cat_name, items in utils.EQUIPMENT_DATA.get('armor', {}).items():

                for item in items:

                    if item.get('name') == item_name:
                        found_item = item

                        break

                if found_item:
                    break

            if found_item:

                char['inventory']['armor'].append({

                    'name': found_item['name'],

                    'ac': found_item.get('ac', '10'),

                    'stealth': found_item.get('stealth'),

                    'strength_req': found_item.get('strength_requirement'),

                    'equipped': False,

                    'cost': found_item.get('cost'),

                    'weight': found_item.get('weight')

                })

            else:

                char['inventory']['armor'].append({

                    'name': item_name,

                    'ac': '10',

                    'equipped': False,

                    'cost': cost_str

                })
        else:
            name_lower = item_name.lower()
            if 'стрел' in name_lower or 'arrow' in name_lower:
                existing = next((a for a in char['inventory']['arrows'] if a['name'] == item_name), None)
                if existing:
                    existing['qty'] += 1
                else:
                    char['inventory']['arrows'].append({
                        'name': item_name,
                        'extra_dmg': 0,
                        'qty': 20
                    })
            elif 'болт' in name_lower or 'bolt' in name_lower:
                existing = next((b for b in char['inventory']['bolts'] if b['name'] == item_name), None)
                if existing:
                    existing['qty'] += 1
                else:
                    char['inventory']['bolts'].append({
                        'name': item_name,
                        'extra_dmg': 0,
                        'qty': 20
                    })
            else:
                existing = next((g for g in char['inventory']['gear'] if g['name'] == item_name), None)
                if existing:
                    existing['qty'] += 1
                else:
                    char['inventory']['gear'].append({
                        'name': item_name,
                        'cost': cost_str,
                        'qty': 1
                    })

        save_chars(current_user['username'], chars)
    except Exception as e:
        print(f"️ Ошибка покупки: {e}")

    return RedirectResponse(url=f"/char/{char_id}/inventory", status_code=303)


@router.post("/char/{char_id}/equipment/custom")
async def add_custom_equipment(char_id: int, request: Request, current_user: dict = Depends(require_player)):
    check_character_ownership(char_id, current_user['username'])
    form = await request.form()

    chars = load_chars(current_user['username'])
    char = next((c for c in chars if c['id'] == char_id), None)

    if not char:
        return RedirectResponse(url="/chars", status_code=303)

    char = normalize_char(char)
    item_type = form.get('item_type')

    try:
        if item_type == 'weapon':
            dmg_x = form.get('dmg_x', '1')
            dmg_y = form.get('dmg_y', '8')

            try:
                dmg_z = int(form.get('dmg_z') or 0)
            except (ValueError, TypeError):
                dmg_z = 0

            dmg_str = f"{dmg_x}d{dmg_y}" + (f"+{dmg_z}" if dmg_z > 0 else "")

            props = form.getlist('weapon_props')
            w_type = 'ammunition' if 'ammunition' in props else (
                'thrown' if 'thrown' in props else ('finesse' if 'finesse' in props else 'standard'))

            desc_parts = [p for p in props if p]
            custom_desc = form.get('weapon_desc', '').strip()
            if custom_desc:
                desc_parts.append(custom_desc)

            new_weapon = {
                'name': form.get('weapon_name', 'Кастомное оружие').strip() or 'Безымянное',
                'type': w_type,
                'damage': dmg_str,
                'description': ', '.join(desc_parts),
                'proficient': True,
                'ammo_type': form.get('weapon_ammo_type', 'arrows') if (
                        'ammunition' in props or 'thrown' in props) else None,
                'weight': form.get('weapon_weight', '0 фнт.')
            }
            char['inventory']['weapons'].append(new_weapon)

        elif item_type == 'armor':
            base_ac = form.get('armor_ac', '10')
            mod = form.get('armor_mod', 'None')
            ac_str = base_ac if mod == 'None' else f"{base_ac} + модификатор {mod}"

            new_armor = {
                'name': form.get('armor_name', 'Кастомная броня').strip() or 'Безымянная',
                'ac': ac_str,
                'weight': form.get('armor_weight', '0 фнт.'),
                'equipped': False,
                'stealth': None,
                'strength_req': None,
                'description': form.get('armor_desc', '').strip()
            }
            char['inventory']['armor'].append(new_armor)

        else:
            new_gear = {
                'name': form.get('gear_name', 'Кастомный предмет').strip() or 'Безымянный',
                'description': form.get('gear_desc', '').strip(),
                'weight': form.get('gear_weight', '0 фнт.'),
                'qty': 1,
                'cost': '—'
            }
            char['inventory']['gear'].append(new_gear)

        save_chars(current_user['username'], chars)
    except Exception as e:
        print(f"⚠️ Ошибка создания кастомного предмета: {e}")

    return RedirectResponse(url=f"/char/{char_id}/inventory", status_code=303)


@router.post("/char/{char_id}/armor/delete/{idx}")
async def delete_armor(char_id: int, idx: int, current_user: dict = Depends(require_player)):
    check_character_ownership(char_id, current_user['username'])

    chars = load_chars(current_user['username'])
    char = next((c for c in chars if c['id'] == char_id), None)

    if char:
        char = normalize_char(char)
        armor_list = char.get('inventory', {}).get('armor', [])
        if 0 <= idx < len(armor_list):
            armor_list.pop(idx)
            save_chars(current_user['username'], chars)

    return RedirectResponse(url=f"/char/{char_id}/inventory", status_code=303)


@router.post("/char/{char_id}/gear/delete/{idx}")
async def delete_gear(char_id: int, idx: int, current_user: dict = Depends(require_player)):
    check_character_ownership(char_id, current_user['username'])

    chars = load_chars(current_user['username'])
    char = next((c for c in chars if c['id'] == char_id), None)

    if char:
        char = normalize_char(char)
        gear_list = char.get('inventory', {}).get('gear', [])
        if 0 <= idx < len(gear_list):
            gear_list.pop(idx)
            save_chars(current_user['username'], chars)

    return RedirectResponse(url=f"/char/{char_id}/inventory", status_code=303)


@router.post("/char/{char_id}/gear/decrease/{idx}")
async def decrease_gear(char_id: int, idx: int, current_user: dict = Depends(require_player)):
    check_character_ownership(char_id, current_user['username'])

    chars = load_chars(current_user['username'])
    char = next((c for c in chars if c['id'] == char_id), None)

    if char:
        char = normalize_char(char)
        gear_list = char.get('inventory', {}).get('gear', [])
        if 0 <= idx < len(gear_list):
            item = gear_list[idx]
            current_qty = item.get('qty', 1) or 1
            if current_qty > 1:
                item['qty'] = current_qty - 1
            else:
                gear_list.pop(idx)
            save_chars(current_user['username'], chars)

    return RedirectResponse(url=f"/char/{char_id}/inventory", status_code=303)


@router.post("/char/{char_id}/coins/update")
async def update_coins(char_id: int, request: Request, current_user: dict = Depends(require_player)):
    check_character_ownership(char_id, current_user['username'])
    form = await request.form()

    chars = load_chars(current_user['username'])
    char = next((c for c in chars if c['id'] == char_id), None)
    if not char:
        return RedirectResponse(url="/chars", status_code=303)

    char = normalize_char(char)

    try:
        gp_spend = int(form.get('gp') or 0)
    except (ValueError, TypeError):
        gp_spend = 0

    try:
        sp_spend = int(form.get('sp') or 0)
    except (ValueError, TypeError):
        sp_spend = 0

    try:
        cp_spend = int(form.get('cp') or 0)
    except (ValueError, TypeError):
        cp_spend = 0

    if gp_spend > 0 and gp_spend > char['inventory']['coins']['gp']:
        return RedirectResponse(url=f"/char/{char_id}/inventory", status_code=303)
    if sp_spend > 0 and sp_spend > char['inventory']['coins']['sp']:
        return RedirectResponse(url=f"/char/{char_id}/inventory", status_code=303)
    if cp_spend > 0 and cp_spend > char['inventory']['coins']['cp']:
        return RedirectResponse(url=f"/char/{char_id}/inventory", status_code=303)

    if gp_spend > 0: char['inventory']['coins']['gp'] -= gp_spend
    if sp_spend > 0: char['inventory']['coins']['sp'] -= sp_spend
    if cp_spend > 0: char['inventory']['coins']['cp'] -= cp_spend

    save_chars(current_user['username'], chars)
    return RedirectResponse(url=f"/char/{char_id}/inventory", status_code=303)


@router.post("/char/{char_id}/coins/set")
async def set_coins(
        char_id: int,
        gp: int = Form(0),
        sp: int = Form(0),
        cp: int = Form(0),
        current_user: dict = Depends(require_player)
):
    """Прямое сохранение точного количества монет (вызывается из VTT комнаты)"""
    check_character_ownership(char_id, current_user['username'])

    chars = load_chars(current_user['username'])
    char = next((c for c in chars if c['id'] == char_id), None)

    if not char:
        return {"status": "error", "message": "Персонаж не найден"}

    # Убеждаемся, что структура существует
    char.setdefault('inventory', {}).setdefault('coins', {'cp': 0, 'sp': 0, 'ep': 0, 'gp': 0, 'pp': 0})

    # Обновляем значения (не позволяем уйти в минус)
    char['inventory']['coins']['gp'] = max(0, gp)
    char['inventory']['coins']['sp'] = max(0, sp)
    char['inventory']['coins']['cp'] = max(0, cp)

    save_chars(current_user['username'], chars)

    return {"status": "ok"}


@router.post("/char/{char_id}/weapon/add")
async def add_weapon(char_id: int, request: Request, current_user: dict = Depends(require_player)):
    check_character_ownership(char_id, current_user['username'])
    form = await request.form()

    chars = load_chars(current_user['username'])
    char = next((c for c in chars if c['id'] == char_id), None)

    if char:
        char = normalize_char(char)
        new_weapon = {
            'name': form.get('name', 'Безымянное оружие'),
            'type': form.get('type', 'standard'),
            'damage': form.get('damage', '1d4'),
            'ammo_type': form.get('ammo_type') if form.get('type') == 'ammunition' else None,
            'description': form.get('description', ''),
            'proficient': form.get('proficient') == 'on'
        }
        char['inventory']['weapons'].append(new_weapon)
        save_chars(current_user['username'], chars)

    return RedirectResponse(url=f"/char/{char_id}/inventory", status_code=303)


@router.post("/char/{char_id}/weapon/delete/{idx}")
async def delete_weapon(char_id: int, idx: int, current_user: dict = Depends(require_player)):
    check_character_ownership(char_id, current_user['username'])

    chars = load_chars(current_user['username'])
    char = next((c for c in chars if c['id'] == char_id), None)

    if char and 0 <= idx < len(char['inventory']['weapons']):
        char['inventory']['weapons'].pop(idx)
        save_chars(current_user['username'], chars)

    return RedirectResponse(url=f"/char/{char_id}/inventory", status_code=303)


@router.get("/char/{char_id}/spells", response_class=HTMLResponse)
async def view_spells(char_id: int, request: Request, current_user: dict = Depends(require_player)):
    char = check_character_ownership(char_id, current_user['username'])

    char = normalize_char(char)
    char_class = char.get('char_class', '')
    char_level = char.get('level', 1)

    known_spells_names = char.get('inventory', {}).get('known_spells', [])

    # 🆕 Получаем все заклинания из БД напрямую
    all_spells = get_all_spells()

    # Разделяем на известные и доступные
    known_spells = [s for s in all_spells if s.get('name_ru') in known_spells_names]
    available_spells = [s for s in all_spells if s.get('name_ru') not in known_spells_names]

    # Определяем тип подготовщика
    is_prepared_caster = char_class.lower() in ['жрец', 'друид', 'паладин', 'волшебник', 'изобретатель']

    def get_level(spell):
        try:
            return int(spell.get('level', 0))
        except (ValueError, TypeError):
            return 0

    known_cantrips = [s for s in known_spells if get_level(s) == 0]
    known_spells_only = [s for s in known_spells if get_level(s) > 0]
    available_cantrips = [s for s in available_spells if get_level(s) == 0]
    available_spells_only = [s for s in available_spells if get_level(s) > 0]

    max_cantrips = None
    max_spells = None

    if char_class in CLASSES_DATA:
        cls_data = CLASSES_DATA[char_class]
        for entry in cls_data.get('level_table', []):
            if entry.get('level', 0) <= char_level:
                if 'cantrips_known' in entry:
                    max_cantrips = max(max_cantrips or 0, entry['cantrips_known'])
                if 'spells_known' in entry:
                    max_spells = max(max_spells or 0, entry['spells_known'])

    return templates.TemplateResponse(request, "spells.html", context={
        "char": char,
        "available_spells": available_spells,
        "known_spells": known_spells,
        "known_cantrips": known_cantrips,
        "known_spells_only": known_spells_only,
        "available_cantrips": available_cantrips,
        "available_spells_only": available_spells_only,
        "max_cantrips": max_cantrips,
        "max_spells": max_spells,
        "is_prepared_caster": is_prepared_caster,
        "error": None,
        "success": None,
        "info": None
    })


@router.post("/char/{char_id}/spells/learn")
async def learn_spell(char_id: int, spell_name: str = Form(...), current_user: dict = Depends(require_player)):
    check_character_ownership(char_id, current_user['username'])

    chars = load_chars(current_user['username'])
    char = next((c for c in chars if c['id'] == char_id), None)

    if char:
        char = normalize_char(char)
        char.setdefault('inventory', {}).setdefault('known_spells', [])

        if spell_name not in char['inventory']['known_spells']:
            char['inventory']['known_spells'].append(spell_name)
            save_chars(current_user['username'], chars)

    return RedirectResponse(url=f"/char/{char_id}/spells", status_code=303)


@router.post("/char/{char_id}/spells/forget")
async def forget_spell(char_id: int, spell_name: str = Form(...), current_user: dict = Depends(require_player)):
    check_character_ownership(char_id, current_user['username'])

    chars = load_chars(current_user['username'])
    char = next((c for c in chars if c['id'] == char_id), None)

    if char:
        char = normalize_char(char)
        if 'inventory' in char and 'known_spells' in char['inventory']:
            if spell_name in char['inventory']['known_spells']:
                char['inventory']['known_spells'].remove(spell_name)
                save_chars(current_user['username'], chars)

    return RedirectResponse(url=f"/char/{char_id}/spells", status_code=303)


@router.get("/char/{char_id}/features", response_class=HTMLResponse)
async def view_class_features(char_id: int, request: Request, current_user: dict = Depends(require_player)):
    char = check_character_ownership(char_id, current_user['username'])

    char = normalize_char(char)
    features = get_class_features(
        char.get('char_class', ''),
        char.get('subclass', 'Нет'),
        char.get('level', 1)
    )

    return templates.TemplateResponse(request, "class_features.html", context={
        "char": char,
        "features": features,
        "error": None,
        "success": None
    })


@router.post("/char/{char_id}/delete")
async def delete_character(char_id: int, request: Request, current_user: dict = Depends(require_player)):
    """Удаляет персонажа игрока"""
    # 1. Проверяем, что персонаж принадлежит пользователю
    check_character_ownership(char_id, current_user['username'])

    # 2. Выполняем удаление через load_chars/save_chars для поддержки текущей архитектуры
    chars = load_chars(current_user['username'])
    original_length = len(chars)
    chars = [c for c in chars if c['id'] != char_id]

    if len(chars) < original_length:
        save_chars(current_user['username'], chars)

    return RedirectResponse(url="/chars?success=Персонаж+успешно+удалён", status_code=303)