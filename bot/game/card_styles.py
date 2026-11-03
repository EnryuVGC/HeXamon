import re
from dataclasses import dataclass, replace

TEMPLATE = "template"
TEXT = "text"
AVATAR = "avatar"

CHOICES = {TEMPLATE: 32, TEXT: 28, AVATAR: 30}
TEXT_BUTTONS = range(21, 29)
DEFAULT_CHOICE = 1
CUSTOM_COLOR = re.compile(r"#?([0-9a-fA-F]{6})")
MOVED_TEMPLATES = {33: 30, 34: DEFAULT_CHOICE}


@dataclass(frozen=True)
class CardStyle:
    template: int = DEFAULT_CHOICE
    text: int | str = DEFAULT_CHOICE
    avatar: int = DEFAULT_CHOICE


def valid(field: str, value: int) -> bool:
    return field in CHOICES and 1 <= value <= CHOICES[field]


def custom_color(words: str | None) -> str | None:
    match = CUSTOM_COLOR.fullmatch((words or "").strip())
    return f"#{match.group(1).upper()}" if match else None


def style_of(trainer: dict) -> CardStyle:
    saved = trainer.get("card", {})
    template = saved.get(TEMPLATE, DEFAULT_CHOICE)
    return CardStyle(
        template=MOVED_TEMPLATES.get(template, template),
        text=saved.get(TEXT, DEFAULT_CHOICE),
        avatar=saved.get(AVATAR, DEFAULT_CHOICE),
    )


def with_choice(style: CardStyle, field: str, value: int) -> CardStyle:
    return replace(style, **{field: value})


def choice_of(style: CardStyle, field: str) -> int:
    return getattr(style, field)
