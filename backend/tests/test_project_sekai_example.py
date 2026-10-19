"""The isolated Miku example goes through the real API without external services."""

from dataclasses import replace
from pathlib import Path

from eidolon.characters import load_characters
from eidolon.config import Settings
from eidolon.gift_catalog import check_liked_gifts, gifts_path, load_gift_catalog
from eidolon.world import load_world, world_path
from tests.conftest import ClientFactory
from tests.fakes import FakeLLM, system_of
from tests.test_text_turn import send_turn, start_conversation

EXAMPLE = (
    Path(__file__).resolve().parents[2]
    / "examples" / "project-sekai" / "characters.toml"
)


def test_example_loads_without_original_game_assets():
    characters = load_characters(EXAMPLE)
    assert list(characters) == ["miku-school"]
    miku = characters["miku-school"]
    assert miku.name == "初音ミク"
    assert miku.user_role == "同行者"
    assert miku.voice_id == ""
    assert miku.avatar is None and miku.background is None
    assert miku.idol_id is None and miku.default_outfit is None
    assert not miku.photographed
    assert miku.facts
    assert load_world(world_path(EXAMPLE)) is None
    check_liked_gifts(characters, load_gift_catalog(gifts_path(EXAMPLE)))


async def test_example_creates_a_bilingual_text_turn(
    settings: Settings, make_client: ClientFactory,
):
    llm = FakeLLM(["<ja>どの練習から始めたい？</ja><zh>想从哪一幕练习开始？</zh>"])
    isolated = replace(
        settings, characters_path=EXAMPLE, affinity_and_gifts=False,
        embedding=None, rerank=None, judge=None, stand_assets_url=None,
    )
    client = make_client(llm, settings=isolated, voice_configured=False)
    listed = await client.get("/api/characters")
    assert listed.status_code == 200
    assert "miku-school" in listed.text
    assert "mano" not in listed.text
    conversation = await start_conversation(client, "miku-school")
    events = await send_turn(client, conversation, "开始练习")
    assert events[-1]["type"] == "done"
    assert events[-1]["message"]["ja"] == "どの練習から始めたい？"
    assert events[-1]["message"]["zh"] == "想从哪一幕练习开始？"
    prompt = system_of(llm.prompts[-1])
    assert "教室的世界" in prompt
    assert "第一声" in prompt and "不同的节拍" in prompt
    assert "留给明天的音符" in prompt
    assert "同行者" in prompt
    assert "283" not in prompt
    assert "男性，和原作一致" not in prompt
