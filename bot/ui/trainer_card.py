from functools import lru_cache
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

from bot.data import catalog
from bot.game.card_styles import CHOICES, TEMPLATE, CardStyle
from bot.services.trainer_stats import TrainerStats
from bot.ui.texts import text

MONO_FONT = "dejavu_sans_mono"
BOLD_FONT = "dejavu_sans_bold"

PIXEL_SCALE = 4

ROW_SIZE = 46.4
ID_SIZE = 40
RANK_SIZE = 58

ROW_LEFT = 68
ROW_RIGHT = 672
FULL_ROW_RIGHT = 956
ROW_CENTERS = (214, 284, 352, 418, 488)
RANK_LEFT = 716
RANK_CENTER = 68
ID_CENTER = 152
TITLE_POSITION = (60, 48)
BADGES_POSITION = (36, 548)

PORTRAIT_POSITION = (704, 184)
PORTRAIT_PIXELS = 66

GRID_COLUMNS = 4
GRID_CARD_SIZE = (256, 168)
GRID_GAP = 6
GRID_NUMBER_SIZE = 40
GRID_NUMBER_BOX = (56, 52)
GRID_NUMBER_CENTER = (208, 77)
GRID_NUMBER_BACKGROUND = (225, 225, 225, 255)
GRID_NUMBER_INK = "#1A1A1A"
GRID_BACKGROUND = "#000000"


def _enlarged(image: Image.Image) -> Image.Image:
    return image.resize((image.width * PIXEL_SCALE, image.height * PIXEL_SCALE), Image.NEAREST)


@lru_cache(maxsize=None)
def _font(name: str, size: float) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(catalog.font(name)), size)


@lru_cache(maxsize=None)
def _template(number: int) -> Image.Image:
    return Image.open(catalog.card_template(number)).convert("RGBA")


@lru_cache(maxsize=1)
def _title_stencil() -> Image.Image:
    return _enlarged(Image.open(catalog.card_title()).convert("L"))


@lru_cache(maxsize=1)
def _badges_stencil() -> Image.Image:
    return _enlarged(Image.open(catalog.card_badges()).convert("L"))


@lru_cache(maxsize=None)
def _portrait(sprite_name: str) -> Image.Image:
    sprite = Image.open(catalog.trainer_sprite(sprite_name)).convert("RGBA")
    sprite = sprite.crop(sprite.getbbox())
    portrait = Image.new("RGBA", (PORTRAIT_PIXELS, PORTRAIT_PIXELS), (0, 0, 0, 0))
    overflow = max(0, sprite.width - PORTRAIT_PIXELS) // 2
    visible = sprite.crop((overflow, 0, overflow + min(sprite.width, PORTRAIT_PIXELS), min(sprite.height, PORTRAIT_PIXELS)))
    portrait.alpha_composite(visible, ((PORTRAIT_PIXELS - visible.width) // 2, PORTRAIT_PIXELS - visible.height))
    return _enlarged(portrait)


def _paste_label(card: Image.Image, stencil: Image.Image, position: tuple[int, int], colour: str) -> None:
    card.paste(Image.new("RGBA", stencil.size, colour), position, stencil)


def _numbered_template(number: int) -> Image.Image:
    card = _template(number).resize(GRID_CARD_SIZE, Image.LANCZOS)
    center_x, center_y = GRID_NUMBER_CENTER
    box_width, box_height = GRID_NUMBER_BOX
    plate = Image.new("RGBA", GRID_NUMBER_BOX, GRID_NUMBER_BACKGROUND)
    card.alpha_composite(plate, (center_x - box_width // 2, center_y - box_height // 2))
    ImageDraw.Draw(card).text(
        GRID_NUMBER_CENTER,
        str(number),
        font=_font(BOLD_FONT, GRID_NUMBER_SIZE if number < 10 else GRID_NUMBER_SIZE * 3 // 4),
        anchor="mm",
        fill=GRID_NUMBER_INK,
    )
    return card


@lru_cache(maxsize=1)
def template_grid() -> bytes:
    count = CHOICES[TEMPLATE]
    rows = -(-count // GRID_COLUMNS)
    card_width, card_height = GRID_CARD_SIZE
    grid = Image.new(
        "RGBA",
        (GRID_COLUMNS * (card_width + GRID_GAP) + GRID_GAP, rows * (card_height + GRID_GAP) + GRID_GAP),
        GRID_BACKGROUND,
    )
    for index in range(count):
        row, column = divmod(index, GRID_COLUMNS)
        grid.alpha_composite(
            _numbered_template(index + 1),
            (GRID_GAP + column * (card_width + GRID_GAP), GRID_GAP + row * (card_height + GRID_GAP)),
        )
    output = BytesIO()
    grid.convert("RGB").save(output, format="PNG")
    return output.getvalue()


def render(stats: TrainerStats, style: CardStyle) -> bytes:
    card = _template(style.template).copy()
    label_ink = catalog.load("card_templates")[style.template - 1]["label_ink"]
    _paste_label(card, _title_stencil(), TITLE_POSITION, label_ink)
    _paste_label(card, _badges_stencil(), BADGES_POSITION, label_ink)
    card.alpha_composite(_portrait(str(style.avatar)), PORTRAIT_POSITION)

    draw = ImageDraw.Draw(card)
    ink = style.text if isinstance(style.text, str) else catalog.load("card_text_colors")[style.text - 1]["hex"]
    mono = _font(MONO_FONT, ROW_SIZE)
    bold = _font(BOLD_FONT, RANK_SIZE)
    draw.text((RANK_LEFT, RANK_CENTER), text("mystats.card_rank"), font=bold, anchor="lm", fill=ink)
    draw.text((FULL_ROW_RIGHT, RANK_CENTER), str(stats.rank), font=bold, anchor="rm", fill=ink)
    draw.text(
        (FULL_ROW_RIGHT, ID_CENTER),
        text("mystats.card_id", id=stats.trainer_id),
        font=_font(MONO_FONT, ID_SIZE),
        anchor="rm",
        fill=ink,
    )
    rows = (
        ("card_exp", f"{stats.exp_points:,}", ROW_RIGHT),
        ("card_next", f"{stats.to_next_rank:,}", ROW_RIGHT),
        ("card_wins", f"{stats.wins:,}", ROW_RIGHT),
        ("card_losses", f"{stats.losses:,}", ROW_RIGHT),
        ("card_started", stats.started_at.strftime("%b %d, %Y"), FULL_ROW_RIGHT),
    )
    for center, (label, value, right) in zip(ROW_CENTERS, rows):
        draw.text((ROW_LEFT, center), text(f"mystats.{label}"), font=mono, anchor="lm", fill=ink)
        draw.text((right, center), value, font=mono, anchor="rm", fill=ink)
    output = BytesIO()
    card.convert("RGB").save(output, format="PNG")
    return output.getvalue()
