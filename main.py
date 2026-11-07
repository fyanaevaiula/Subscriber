import json
import re
import uuid
from datetime import datetime, date
from enum import Enum
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator, EmailStr

app = FastAPI(title="Сервис сбора обращений абонентов")

# Папка, куда складываются json-файлы с обращениями
STORAGE_DIR = Path("appeals")
STORAGE_DIR.mkdir(exist_ok=True)


class AppealReason(str, Enum):
    """Возможные причины обращения."""
    NO_NETWORK = "нет доступа к сети"
    PHONE_NOT_WORKING = "не работает телефон"
    NO_EMAILS = "не приходят письма"


class Appeal(BaseModel):
    """Модель обращения абонента."""

    surname: str = Field(..., description="Фамилия")
    name: str = Field(..., description="Имя")
    birth_date: date = Field(..., description="Дата рождения")
    phone: str = Field(..., description="Номер телефона")
    email: EmailStr = Field(..., description="E-mail")
    reason: AppealReason = Field(..., description="Причина обращения")
    problem_datetime: datetime = Field(..., description="Дата и время обнаружения проблемы")

    # ---- Валидатор фамилии и имени ----
    @field_validator("surname", "name")
    @classmethod
    def validate_person_name(cls, value: str) -> str:
        value = value.strip()
        # только кириллица (пробел и дефис допускаем для двойных фамилий)
        if not re.fullmatch(r"[А-ЯЁа-яё-]+(?: [А-ЯЁа-яё-]+)?", value):
            raise ValueError("допустимы только кириллические буквы, дефис и пробел")
        # первая буква заглавная, остальные — строчные
        first, *rest = value.split(" ")
        for part in [first, *rest]:
            if not (part[0].isupper() and part[1:].islower()):
                raise ValueError("каждая часть должна начинаться с заглавной буквы")
        return value

    # ---- Валидатор даты рождения ----
    @field_validator("birth_date")
    @classmethod
    def validate_birth_date(cls, value: date) -> date:
        today = date.today()
        if value > today:
            raise ValueError("дата рождения не может быть в будущем")
        if today.year - value.year > 120:
            raise ValueError("слишком давняя дата рождения")
        return value

    # ---- Валидатор номера телефона ----
    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        digits = re.sub(r"[ \-()]", "", value)  # убираем пробелы, дефисы, скобки
        if not re.fullmatch(r"(\+?7|8)\d{10}", digits):
            raise ValueError(
                "номер должен быть российским: +7XXXXXXXXXX или 8XXXXXXXXXX"
            )
        # нормализуем к единому виду +7XXXXXXXXXX
        return "+7" + digits[-10:]

    # ---- Валидатор даты и времени обнаружения проблемы ----
    @field_validator("problem_datetime")
    @classmethod
    def validate_problem_datetime(cls, value: datetime) -> datetime:
        if value > datetime.now():
            raise ValueError("время обнаружения проблемы не может быть в будущем")
        return value


@app.post("/appeals", status_code=201)
def create_appeal(appeal: Appeal) -> dict:
    """Принимает обращение и сохраняет его в json-файл на диске."""
    try:
        record = appeal.model_dump(mode="json")
        record["id"] = str(uuid.uuid4())
        record["created_at"] = datetime.now().isoformat()

        file_path = STORAGE_DIR / f"{record['id']}.json"
        file_path.write_text(
            json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Ошибка записи на диск: {e}")

    return {"message": "Обращение сохранено", "id": record["id"], "file": str(file_path)}


@app.get("/appeals")
def list_appeals() -> list[dict]:
    """Возвращает список всех сохранённых обращений."""
    appeals = []
    for f in STORAGE_DIR.glob("*.json"):
        appeals.append(json.loads(f.read_text(encoding="utf-8")))
    return appeals
