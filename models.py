from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
import re

# === Аутентификация ===
class UserLogin(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=4)
    action: str = Field(..., pattern="^(login|register)$")
    role: Optional[str] = Field(None, pattern="^(player|master)$")

class UserRegister(UserLogin):
    @validator('username')
    def username_alphanumeric(cls, v):
        if not re.match(r'^[a-zA-Z0-9_]+$', v):
            raise ValueError('Логин может содержать только буквы, цифры и _')
        return v.lower()

class TokenData(BaseModel):
    username: str
    role: str

# === Персонаж ===
class Stat(BaseModel):
    score: int = Field(ge=1, le=30)
    modifier: int = Field(default=0)

class Physical(BaseModel):
    height: str = ""
    weight: str = ""
    hair: str = ""
    eyes: str = ""

class Coins(BaseModel):
    cp: int = 0
    sp: int = 0
    ep: int = 0
    gp: int = 0
    pp: int = 0

class Inventory(BaseModel):
    weapons: List[Dict[str, Any]] = []
    armor: List[Dict[str, Any]] = []
    gear: List[Dict[str, Any]] = []
    arrows: List[Dict[str, Any]] = []
    bolts: List[Dict[str, Any]] = []
    coins: Coins = Coins()
    known_spells: List[str] = []
    items: List[Dict[str, Any]] = []

class CharacterCreate(BaseModel):
    name: str = Field(..., min_length=1)
    race: str
    char_class: str
    subclass: Optional[str] = "Нет"
    alignment: str
    xp: int = Field(default=0, ge=0)
    physical: Physical = Physical()
    stats: Dict[str, Stat]
    saving_throws: List[str] = []
    skills: List[str] = []
    ac: str = "10"
    initiative: str = "+0"
    speed: str = "30 фт"
    prof_bonus: str = "+2"
    hp_current: int = Field(ge=0)
    hp_max: int = Field(ge=0)
    hp_temp: int = Field(default=0, ge=0)
    description: str = ""
    features_spells: str = ""

class CharacterUpdate(BaseModel):
    name: Optional[str] = None
    xp: Optional[int] = None
    hp_current: Optional[int] = None
    hp_temp: Optional[int] = None
    # ... другие поля для обновления

# === Комнаты ===
class RoomCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = ""
    max_players: int = Field(default=6, ge=1, le=10)

class RoomPlayer(BaseModel):
    username: str
    char_id: int
    last_active: Optional[float] = None

class RewardRequest(BaseModel):
    xp: int = Field(default=0, ge=0)
    coins: Dict[str, int] = Field(default_factory=lambda: {"cp":0,"sp":0,"ep":0,"gp":0,"pp":0})
    target: str = "all"  # 'all' или char_id
    reason: Optional[str] = ""

    @validator('coins')
    def coins_non_negative(cls, v):
        if any(val < 0 for val in v.values()):
            raise ValueError('Количество монет не может быть отрицательным')
        return v

# === Броски кубиков ===
class RollRequest(BaseModel):
    char_name: str
    type: str = "roll"  # 'attack', 'check', 'skill', 'plain'
    dice: str = "d20"
    roll: int
    modifier: int = 0
    total: int
    is_crit: bool = False
    is_fail: bool = False
    description: Optional[str] = ""

# === Боеприпасы ===
class AmmoUseRequest(BaseModel):
    ammo_type: str = Field(..., pattern="^(arrows|bolts)$")
    qty: int = Field(default=1, ge=1)

class TokenUpload(BaseModel):
    image: str  # base64 data URL


class SpellCreate(BaseModel):
    name_ru: str
    name_en: str
    level: int
    school: str
    casting_time: str
    range: str
    components: str
    duration: str
    description: str
    source: Optional[str] = None
    classes: List[str] = []