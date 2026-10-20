"""A character's current user identity, independent of the original producer."""

import json
from datetime import UTC, datetime

import pytest

from eidolon.characters import CharacterConfigError, load_characters
from eidolon.producer import Birthday, ProducerProfile, now_prompt, producer_prompt
from tests.conftest import CharacterConfig, ClientFactory
from tests.fakes import FakeLLM, system_of
from tests.test_text_turn import send_turn, start_conversation

ROLE = "同行者"
IDENTITY = "在「世界」中与初音未来相遇、一起分享日常的同行者"
NOW = datetime(2026, 5, 2, 15, 30, tzinfo=UTC)
REPLY = ["<ja>こんにちは！</ja><zh>你好！</zh>"]


def configure_identity(characters: CharacterConfig, fields: dict) -> None:
    """Append fields to the configuration's last character, as a deployer would."""
    with characters.path.open("a", encoding="utf-8") as config:
        for field, value in fields.items():
            config.write(f"{field} = {json.dumps(value, ensure_ascii=False)}\n")


def test_custom_identity_is_loaded_and_trimmed(characters: CharacterConfig):
    configure_identity(
        characters, {"user_role": f"  {ROLE}  ", "user_identity": f"  {IDENTITY}  "}
    )

    loaded = load_characters(characters.path)

    assert loaded["kogane"].user_role == ROLE
    assert loaded["kogane"].user_identity == IDENTITY
    assert loaded["mano"].user_role is None
    assert loaded["mano"].user_identity is None


@pytest.mark.parametrize("missing", ["user_role", "user_identity"])
def test_identity_fields_must_be_configured_together(
    characters: CharacterConfig, missing: str
):
    fields = {"user_role": ROLE, "user_identity": IDENTITY}
    del fields[missing]
    configure_identity(characters, fields)

    with pytest.raises(CharacterConfigError, match="须同时配置"):
        load_characters(characters.path)


@pytest.mark.parametrize("field", ["user_role", "user_identity"])
@pytest.mark.parametrize(
    "value", ["", "  ", "一\n二", "一\r二", "一\n", "\n一", "一\u2028二", 7, True, []]
)
def test_identity_fields_must_be_nonempty_single_line_strings(
    characters: CharacterConfig, field: str, value: object
):
    fields: dict = {"user_role": ROLE, "user_identity": IDENTITY}
    fields[field] = value
    configure_identity(characters, fields)

    with pytest.raises(CharacterConfigError, match=field):
        load_characters(characters.path)


def test_default_identity_keeps_the_original_prompt():
    assert producer_prompt(ProducerProfile()) == (
        "# 制作人\n和你对话的是你的制作人，也就是 283 事务所的制作人。\n"
        "制作人是男性，和原作一致。"
    )
    assert now_prompt(ProducerProfile(), NOW, "Asia/Tokyo", False) == (
        "# 此刻\n现在是 2026年5月3日（星期日）00:30（制作人所在时区 Asia/Tokyo）。\n"
        "制作人正在用文字和你聊天，你们没有在打电话；不想聊的时候就说不想聊，不要说挂电话或挂断。"
    )


@pytest.mark.parametrize("gender", [None, "female", "male"])
async def test_each_text_turn_uses_its_characters_identity_and_user_profile(
    characters: CharacterConfig, make_client: ClientFactory, gender: str | None
):
    characters.add("miku", "初音未来", "你是初音未来，和来访者分享日常。")
    configure_identity(characters, {"user_role": ROLE, "user_identity": IDENTITY})
    llm = FakeLLM(REPLY, REPLY, REPLY)
    client = make_client(llm, clock=lambda: NOW)
    client.headers["X-Timezone"] = "America/Los_Angeles"
    response = await client.put(
        "/api/profile",
        json={
            "form_of_address": "小林さん",
            "gender": gender,
            "timezone": "Asia/Tokyo",
            "birthday": {"month": 5, "day": 3},
        },
    )
    assert response.status_code == 200
    conversation = await start_conversation(client, "miku")

    for text in ("你好", "今天是什么日子？"):
        events = await send_turn(client, conversation, text)
        assert events[-1]["type"] == "done"
        prompt = "\n\n".join(
            message.content for message in llm.prompts[-1] if message.role == "system"
        )
        assert IDENTITY in prompt
        assert f"{ROLE}希望你称呼对方为「小林さん」" in prompt
        assert f"{ROLE}的生日是5月3日" in prompt
        assert f"今天是{ROLE}的生日" in prompt
        assert "2026年5月3日" in prompt and "00:30" in prompt
        assert f"{ROLE}所在时区 Asia/Tokyo" in prompt
        assert f"{ROLE}正在用文字和你聊天" in prompt
        assert "283" not in prompt
        assert "仍然是你的制作人" not in prompt
        assert "和你对话的是你的制作人" not in prompt
        assert f"{ROLE}要你发照片时" in prompt
        assert "制作人要你发照片时" not in prompt
        if gender is None:
            assert "男性" not in prompt and "女性" not in prompt
        else:
            assert f"{ROLE}是{'女性' if gender == 'female' else '男性'}" in prompt
            assert "剧情中发生过的事保持原样" in prompt

    original = await start_conversation(client, "mano")
    await send_turn(client, original, "你好")
    prompt = system_of(llm.prompts[-1])
    assert "283 事务所的制作人" in prompt
    assert "对方仍然是你的制作人" in prompt
    assert IDENTITY not in prompt


@pytest.mark.parametrize("in_call", [False, True], ids=["typing", "calling"])
@pytest.mark.parametrize(
    ("timezone", "birthday"), [("Asia/Tokyo", True), ("Asia/Shanghai", False)]
)
def test_custom_identity_in_current_time_call_and_birthday_context(
    in_call: bool, timezone: str, birthday: bool
):
    profile = ProducerProfile(birthday=Birthday(5, 3))

    prompt = now_prompt(
        profile, NOW, timezone, in_call, ["亲近地回应。"], user_role=ROLE
    )

    assert "制作人" not in prompt
    assert f"{ROLE}所在时区 {timezone}" in prompt
    assert (f"今天是{ROLE}的生日" in prompt) is birthday
    if in_call:
        assert f"{ROLE}正在和你打电话。" in prompt
    else:
        assert f"{ROLE}正在用文字和你聊天" in prompt
    assert prompt.endswith("亲近地回应。")
