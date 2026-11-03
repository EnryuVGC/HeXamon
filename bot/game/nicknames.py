MAX_NICKNAME_LENGTH = 12


def clean_nickname(raw: str) -> str | None:
    nickname = raw.strip()
    if not 1 <= len(nickname) <= MAX_NICKNAME_LENGTH or "\n" in nickname:
        return None
    return nickname
