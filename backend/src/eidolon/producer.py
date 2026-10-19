"""The producer profile and what it tells the character about the user, and the prompt
section about now: the time where the user is, and whether they are typing or in a call.

A profile field left unset keeps its default: the character sheet decides how
the character addresses the producer, the producer is the man of the original
story, the time zone is the one the user's device reports (Asia/Shanghai
when it reports none), and the character does not know the producer's birthday
(a month and a day, never a year). On the birthday, counted in the producer's
own time zone, the character is asked to wish them a happy birthday once. The
profile only shapes how the character treats the user now; the stories she
recalls stay as they happened.

A character may configure a different current user role and identity. Those replace
the producer context, and an unset gender then makes no gender assumption. The user's
form of address, gender, time zone and birthday still apply.
"""

import calendar
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from functools import cache
from typing import Literal
from zoneinfo import ZoneInfo, available_timezones

Gender = Literal["male", "female"]

DEFAULT_TIMEZONE = "Asia/Shanghai"
MAX_FORM_OF_ADDRESS_LENGTH = 20

_GENDER_NAMES: dict[Gender, str] = {"male": "男性", "female": "女性"}
_WEEKDAYS = "一二三四五六日"


@dataclass(frozen=True)
class Birthday:
    """The producer's birthday: a month and a day, never a year."""

    month: int
    day: int


def is_day_of_the_year(month: int, day: int) -> bool:
    """Whether some year has this day; February 29 counts."""
    return 1 <= month <= 12 and 1 <= day <= calendar.monthrange(2000, month)[1]


def is_birthday(birthday: Birthday, today: date) -> bool:
    """Whether `today`, the producer's local date, is their birthday.

    February 29 falls on February 28 in a year that has no February 29.
    """
    if (birthday.month, birthday.day) == (today.month, today.day):
        return True
    return (
        (birthday.month, birthday.day) == (2, 29)
        and (today.month, today.day) == (2, 28)
        and not calendar.isleap(today.year)
    )


@dataclass(frozen=True)
class ProducerProfile:
    form_of_address: str | None = None
    gender: Gender | None = None
    timezone: str | None = None
    birthday: Birthday | None = None


@cache
def _known_timezones() -> frozenset[str]:
    # The server's own local time is no place a user lives in.
    return frozenset(available_timezones() - {"localtime", "Factory"})


def is_timezone(name: str) -> bool:
    """Whether `name` is an IANA time zone, such as Asia/Tokyo."""
    return name in _known_timezones()


def effective_timezone(profile: ProducerProfile, device_timezone: str | None) -> str:
    """The profile's time zone if set, else the device's, else Asia/Shanghai.

    Either may name a zone this server does not know (tzdata drops or renames
    zones now and then); such a zone is passed over rather than failing the turn.
    """
    for timezone in (profile.timezone, device_timezone):
        if timezone and is_timezone(timezone):
            return timezone
    return DEFAULT_TIMEZONE


def local_date(now: datetime, timezone: str) -> date:
    """The day it is at `now` where the producer is: the day `now_prompt` tells."""
    return now.astimezone(ZoneInfo(timezone)).date()


def producer_prompt(
    profile: ProducerProfile,
    *,
    user_role: str | None = None,
    user_identity: str | None = None,
) -> str:
    """The prompt section about the user: who they are, the same from turn to turn."""
    custom_identity = user_role is not None and user_identity is not None
    role = user_role if custom_identity else "制作人"
    lines = (
        [f"# {role}", f"和你对话的是{user_identity}。"]
        if custom_identity
        else ["# 制作人", "和你对话的是你的制作人，也就是 283 事务所的制作人。"]
    )
    if profile.form_of_address:
        identity_reminder = "" if custom_identity else "对方仍然是你的制作人；"
        lines.append(
            f"{role}希望你称呼对方为「{profile.form_of_address}」。这只是叫法，"
            f"{identity_reminder}请按你自己的性格和习惯，在合适的时候这样称呼。"
        )
    if profile.gender:
        lines.append(
            f"{role}是{_GENDER_NAMES[profile.gender]}。这只影响你现在怎么对待对方；"
            "回忆原作剧情时，剧情中发生过的事保持原样，不要改写。"
        )
    elif not custom_identity:
        lines.append("制作人是男性，和原作一致。")
    if profile.birthday:
        lines.append(
            f"{role}的生日是{profile.birthday.month}月{profile.birthday.day}日，"
            f"这是{role}自己在档案里填的；记忆里如果有不一样的说法，以这里为准。"
            "被问起时可以回答，平时不要主动提起。"
        )
    return "\n".join(lines)


_TYPING = "制作人正在用文字和你聊天，你们没有在打电话；不想聊的时候就说不想聊，不要说挂电话或挂断。"
_IN_A_CALL = "制作人正在和你打电话。"


def now_prompt(
    profile: ProducerProfile,
    now: datetime,
    timezone: str,
    in_call: bool,
    affinity_lines: Sequence[str] = (),
    *,
    user_role: str | None = None,
) -> str:
    """The prompt section about now: the time where the user is, whether they are typing or
    `in_call` with the character, and whether it is their birthday; then `affinity_lines`,
    how the character feels toward them now (`affinity.affinity_prompt`)."""
    local = now.astimezone(ZoneInfo(timezone))
    role = user_role if user_role is not None else "制作人"
    lines = [
        "# 此刻",
        f"现在是 {local.year}年{local.month}月{local.day}日"
        f"（星期{_WEEKDAYS[local.weekday()]}）{local:%H:%M}（{role}所在时区 {timezone}）。",
        (_IN_A_CALL if in_call else _TYPING).replace("制作人", role),
    ]
    if profile.birthday and is_birthday(profile.birthday, local.date()):
        lines.append(
            f"今天是{role}的生日。请在合适的时候用你自己的方式祝福一次："
            f"先回应{role}说的话，不要每句都提。"
        )
    lines += affinity_lines
    return "\n".join(lines)
