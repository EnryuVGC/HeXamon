from bot.data import catalog


def text(key: str, **values) -> str:
    entry = catalog.load("texts")
    for part in key.split("."):
        entry = entry[part]
    return entry.format(**values)
