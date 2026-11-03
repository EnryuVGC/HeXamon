from html import escape

from bot.game import referrals as rules
from bot.game.inventory import stone_name
from bot.ui.texts import text


def stats_text(count: int) -> str:
    return text(
        "referrals.stats",
        count=count,
        bonus=rules.INVITE_REWARD,
        exp=rules.TARGET_EXP,
        balls_every=rules.BALLS_EVERY,
        stone_every=rules.STONE_EVERY,
        master_every=rules.MASTER_EVERY,
    )


def joined_text(name: str) -> str:
    return text("referrals.joined", name=escape(name), exp=rules.TARGET_EXP)


def payout_text(name: str, count: int, milestone: rules.Milestone, bonus: int) -> str:
    lines = []
    if milestone.balls:
        lines.append(text("referrals.reward_balls", **rules.BALL_MIX))
    if milestone.tm:
        lines.append(text("referrals.reward_tm", number=milestone.tm))
    if milestone.master:
        lines.append(text("referrals.reward_master"))
    reached_key = "referrals.reached" if bonus else "referrals.reached_limit"
    reached = text(reached_key, name=escape(name), exp=rules.TARGET_EXP, bonus=bonus)
    if not lines:
        return reached
    return text("referrals.milestone", reached=reached, count=count, rewards="\n".join(lines))


def stone_text(count: int, stone: str) -> str:
    return text("referrals.reward_stone", count=count, stone=stone_name(stone))
