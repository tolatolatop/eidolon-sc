"""Real pinned G2P regression tests; no ONNX model, audio inference or downloads."""

import pytest
from kokoro_onnx.config import DEFAULT_VOCAB
from misaki.cutlet import Cutlet
from misaki.zh import ZHG2P
from server import phoneme_chunks


@pytest.fixture(scope="module")
def japanese():
    return Cutlet()


@pytest.mark.parametrize("text", [
    "あいうえお、かきくけこ、さしすせそ、たちつてと、なにぬねの。",
    "はひふへほ、まみむめも、やゆよ、らりるれろ、わをん。",
    "がぎぐげご、ざじずぜぞ、だぢづでど、ばびぶべぼ、ぱぴぷぺぽ。",
    "きゃきゅきょ、ぎゃぎゅぎょ、しゃしゅしょ、じゃじゅじょ、ちゃちゅちょ。",
    "にゃにゅにょ、ひゃひゅひょ、びゃびゅびょ、ぴゃぴゅぴょ、みゃみゅみょ、りゃりゅりょ。",
    "今日も一緒に練習しよう。気持ちをゆっくり言葉にしてね。",
])
def test_official_cutlet_phonemes_are_fully_covered_by_v1_vocabulary(japanese, text):
    chunks = phoneme_chunks(japanese, text, DEFAULT_VOCAB)
    assert chunks
    assert all(set(chunk) <= DEFAULT_VOCAB.keys() for chunk in chunks)


def test_today_crosses_former_sixty_character_boundary_without_splitting(japanese):
    text = "あ" * 59 + "今日も一緒に練習しよう。"
    seen = []

    def converter(value):
        seen.append(value)
        return japanese(value)

    chunks = phoneme_chunks(converter, text, DEFAULT_VOCAB)
    expected = " ".join(japanese(text)[0].split())
    today = japanese("今日")[0]
    assert seen == [text]
    assert "".join(chunks) == expected
    assert today in expected


def test_official_chinese_g2p_uses_v1_vocabulary():
    assert phoneme_chunks(ZHG2P(), "你好，今天也一起练习吧。", DEFAULT_VOCAB)
