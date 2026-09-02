"""
Pydantic-схемы для WebSocket-сообщений комнаты.

Каждое сообщение от клиента проходит через схему ДО любой обработки и
сохранения в Redis. Схемы:
  * задают структуру и типы полей для каждого типа сообщения;
  * ограничивают длину строк (текст чата, имена, URL изображений);
  * ограничивают диапазоны чисел (координаты, HP, размеры, толщина линий);
  * отбрасывают неизвестные поля (extra='ignore'), не давая протащить в
    состояние комнаты произвольный «мусор».
"""
from typing import Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

# === Лимиты ===
MAX_TEXT_LEN = 2000          # текст чата
MAX_NAME_LEN = 200           # имена персонажей/токенов/проверок
MAX_TOKEN_ID_LEN = 128       # идентификаторы токенов/персонажей
MAX_URL_LEN = 2048           # URL изображений (S3/media)
MAX_COORD = 1_000_000.0      # координаты на карте
MAX_SIZE = 1_000_000.0       # ширина/высота/размер токена, толщина линии
MAX_NUMBER = 1_000_000_000   # HP/инициатива/модификаторы/броски
MAX_PATH_POINTS = 20_000     # точек в ломаной (рисование/туман/линейка)

IdType = Union[str, int]


class _Base(BaseModel):
    """Базовый класс: незнакомые поля молча отбрасываются."""
    model_config = ConfigDict(extra="ignore")


# === Первое сообщение (рукопожатие) ===
class InitSchema(_Base):
    """Первое сообщение после connect: {username?, char_name?}."""
    username: Optional[str] = Field(None, max_length=MAX_NAME_LEN)
    char_name: Optional[str] = Field(None, max_length=MAX_NAME_LEN)


# === Чат и броски ===
class ChatMessageSchema(_Base):
    type: Literal["chat_message"]
    text: str = Field(..., min_length=1, max_length=MAX_TEXT_LEN)

    @field_validator("text")
    @classmethod
    def _not_blank(cls, v):
        if not v.strip():
            raise ValueError("text не должен состоять из пробелов")
        return v


class DiceRollSchema(_Base):
    type: Literal["dice_roll"]
    name: str = Field("", max_length=MAX_NAME_LEN)
    roll: Optional[int] = Field(None, ge=-MAX_NUMBER, le=MAX_NUMBER)
    sides: Optional[int] = Field(None, ge=1, le=1_000_000)
    modifier: Optional[int] = Field(0, ge=-MAX_NUMBER, le=MAX_NUMBER)
    total: Optional[int] = Field(None, ge=-MAX_NUMBER, le=MAX_NUMBER)
    is_crit: bool = False
    is_fail: bool = False
    is_hidden: bool = False


class PointSchema(_Base):
    x: float = Field(..., ge=-MAX_COORD, le=MAX_COORD)
    y: float = Field(..., ge=-MAX_COORD, le=MAX_COORD)


class MeasureSchema(_Base):
    type: Literal["measure"]
    start: Optional[PointSchema] = None
    end: Optional[PointSchema] = None


# === Карта: рисование / сетка / туман ===
class LineSchema(_Base):
    """Ломаная для рисования на карте (draw_line)."""
    points: list[PointSchema] = Field(..., min_length=2, max_length=MAX_PATH_POINTS)
    color: str = Field("#e0d4b8", max_length=32)
    width: float = Field(2.0, ge=0.5, le=MAX_SIZE)


class DrawLineSchema(_Base):
    type: Literal["draw_line"]
    line: Optional[LineSchema] = None


class FowPathSchema(_Base):
    """Ломаная тумана войны (fow_update action=add_path)."""
    type: Literal["path"] = "path"
    mode: Literal["reveal", "hide"] = "reveal"
    points: list[PointSchema] = Field(..., min_length=2, max_length=MAX_PATH_POINTS)
    width: float = Field(60.0, ge=0.5, le=MAX_SIZE)


class FowUpdateSchema(_Base):
    type: Literal["fow_update"]
    action: Literal["add_path", "hide_all", "clear_all"]
    path: Optional[FowPathSchema] = None


class GridSizeSchema(_Base):
    type: Literal["grid_size_update"]
    grid_size: int = Field(50, ge=5, le=1000)


class DrawClearSchema(_Base):
    type: Literal["draw_clear"]


# === Карта: фон ===
class MapUpdateSchema(_Base):
    type: Literal["map_update"]
    image: Optional[str] = Field(None, max_length=MAX_URL_LEN)
    width: int = Field(0, ge=0, le=1_000_000)
    height: int = Field(0, ge=0, le=1_000_000)


class MapClearSchema(_Base):
    type: Literal["map_clear"]


# === Токены и трекер боя ===
AcType = Union[str, int, float]


class TokenSchema(_Base):
    """Данные токена: что разрешено хранить в состоянии комнаты."""
    token_id: Optional[IdType] = None
    char_id: Optional[IdType] = None
    name: Optional[str] = Field(None, max_length=MAX_NAME_LEN)
    char_name: Optional[str] = Field(None, max_length=MAX_NAME_LEN)
    image: Optional[str] = Field(None, max_length=MAX_URL_LEN)
    x: Optional[float] = Field(None, ge=-MAX_COORD, le=MAX_COORD)
    y: Optional[float] = Field(None, ge=-MAX_COORD, le=MAX_COORD)
    width: Optional[float] = Field(None, ge=0, le=MAX_SIZE)
    height: Optional[float] = Field(None, ge=0, le=MAX_SIZE)
    size: Optional[float] = Field(None, ge=0, le=MAX_SIZE)
    ac: Optional[AcType] = None
    armor_class: Optional[AcType] = None
    initiative: Optional[float] = Field(None, ge=-MAX_NUMBER, le=MAX_NUMBER)
    dex_mod: Optional[int] = Field(None, ge=-1000, le=1000)
    hp_current: Optional[int] = Field(None, ge=-MAX_NUMBER, le=MAX_NUMBER)
    hp_max: Optional[int] = Field(None, ge=-MAX_NUMBER, le=MAX_NUMBER)
    is_monster: Optional[bool] = False
    is_object: Optional[bool] = False

    @field_validator("ac", "armor_class")
    @classmethod
    def _validate_ac(cls, v):
        if isinstance(v, bool):
            raise ValueError("ac не может быть bool")
        if isinstance(v, str) and len(v) > 60:
            raise ValueError("ac слишком длинный")
        return v

    @field_validator("token_id", "char_id")
    @classmethod
    def _validate_id(cls, v):
        if isinstance(v, bool):
            raise ValueError("id не может быть bool")
        if isinstance(v, str) and len(v) > MAX_TOKEN_ID_LEN:
            raise ValueError("id слишком длинный")
        return v


class TokenUpdateSchema(_Base):
    type: Literal["token_update"]
    action: Literal["add", "remove", "move"]
    token: TokenSchema = Field(default_factory=dict)


class CombatantHpSchema(_Base):
    type: Literal["combatant_hp_update"]
    token_id: IdType = Field(...)
    hp_current: int = Field(..., ge=-MAX_NUMBER, le=MAX_NUMBER)

    @field_validator("token_id")
    @classmethod
    def _validate_id(cls, v):
        if isinstance(v, bool):
            raise ValueError("id не может быть bool")
        if isinstance(v, str) and len(v) > MAX_TOKEN_ID_LEN:
            raise ValueError("id слишком длинный")
        return v


class TokensClearSchema(_Base):
    type: Literal["tokens_clear"]


# === Реестр схем по типам сообщений ===
WS_SCHEMAS: dict[str, type[_Base]] = {
    "chat_message": ChatMessageSchema,
    "dice_roll": DiceRollSchema,
    "measure": MeasureSchema,
    "draw_line": DrawLineSchema,
    "draw_clear": DrawClearSchema,
    "fow_update": FowUpdateSchema,
    "grid_size_update": GridSizeSchema,
    "map_update": MapUpdateSchema,
    "map_clear": MapClearSchema,
    "token_update": TokenUpdateSchema,
    "combatant_hp_update": CombatantHpSchema,
    "tokens_clear": TokensClearSchema,
}

