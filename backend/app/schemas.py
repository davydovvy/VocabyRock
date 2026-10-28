from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, field_validator


class WordInput(BaseModel):
    english: str = Field(min_length=1, max_length=160)
    translations: list[str] = Field(min_length=1)
    ipa: str | None = None
    part_of_speech: str | None = None
    example_en: str | None = None
    example_ru: str | None = None
    notes: str | None = None

    @field_validator("english")
    @classmethod
    def clean_english(cls, value: str):
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Add an English word")
        return cleaned

    @field_validator("translations")
    @classmethod
    def clean_translations(cls, value: list[str]):
        cleaned = list(
            dict.fromkeys(" ".join(item.split()).lower() for item in value if item.strip())
        )
        if not cleaned:
            raise ValueError("Add at least one translation")
        return cleaned


class WordSaveInput(WordInput):
    audio_url: str | None = None


class WordOut(WordInput):
    model_config = ConfigDict(from_attributes=True)
    id: int
    picture: str | None
    audio: str | None
    audio_status: str | None
    audio_error: str | None
    created_at: datetime
    updated_at: datetime


class PixabaySelection(BaseModel):
    image_id: int = Field(gt=0)


class PackInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = ""
    category: str | None = None

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str):
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Add a pack name")
        return cleaned


class PackOut(PackInput):
    model_config = ConfigDict(from_attributes=True)
    id: int
    cover: str | None
    word_ids: list[int] = []
    word_count: int = 0
    learned_count: int = 0


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    role: str
    name: str
    avatar: str
    sound_enabled: bool
    xp: int
    stars: int


class ProfileInput(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    avatar: str | None = None
    sound_enabled: bool | None = None

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str | None):
        if value is None:
            return None
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Add a name")
        return cleaned


class SettingsInput(BaseModel):
    session_length: int = Field(ge=1, le=30)
    accent: str = Field(pattern="^en-(US|GB)$")
    direction: str = Field(pattern="^(en-ru|ru-en)$")
    fold_yo: bool
    lenient_typos: bool
    allowed_exercises: list[str]
    child_avatar_change: bool

    @field_validator("allowed_exercises")
    @classmethod
    def validate_exercises(cls, value: list[str]):
        allowed = {"match", "flashcard", "choice", "type", "listen"}
        if not value or not set(value) <= allowed:
            raise ValueError("Select at least one valid exercise")
        return list(dict.fromkeys(value))


class SessionStart(BaseModel):
    pack_id: int | None = None
    mode: str = Field(default="quick", pattern="^(quick|new|practice|hard|all|mistakes)$")
    kind: str | None = Field(
        default=None, pattern="^(match|match_all|flashcard|choice|type|listen)$"
    )
    direction: str | None = Field(default=None, pattern="^(en-ru|ru-en)$")
    length: int | None = Field(default=None, ge=1, le=30)
    word_ids: list[int] | None = None


class AnswerInput(BaseModel):
    index: int = Field(ge=0)
    answer: str | None = None
    option_id: int | None = None
    rating: str | None = Field(default=None, pattern="^(again|hard|easy)$")


class HintInput(BaseModel):
    level: int = Field(ge=1, le=2)


class MatchPairInput(BaseModel):
    index: int = Field(ge=0)
    option_id: int = Field(ge=0)


class MatchAllInput(BaseModel):
    pairs: list[MatchPairInput]


class ResetInput(BaseModel):
    child_id: int
    word_id: int | None = None
    pack_id: int | None = None
    confirm: bool
