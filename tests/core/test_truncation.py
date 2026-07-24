from app.core.truncation import (
    BODY_MAX_CHARS,
    COMMENT_MAX_CHARS,
    truncate_body,
    truncate_comment,
)


def test_truncate_body_none():
    assert truncate_body(None) == "(no description provided)"


def test_truncate_body_empty():
    assert truncate_body("") == "(no description provided)"


def test_truncate_body_short():
    text = "This is a short body."
    assert truncate_body(text) == text


def test_truncate_body_long():
    text = "x" * (BODY_MAX_CHARS + 100)
    result = truncate_body(text)
    assert len(result) == BODY_MAX_CHARS


def test_truncate_comment_none():
    assert truncate_comment(None) == ""


def test_truncate_comment_empty():
    assert truncate_comment("") == ""


def test_truncate_comment_short():
    text = "Short comment."
    assert truncate_comment(text) == text


def test_truncate_comment_long():
    text = "y" * (COMMENT_MAX_CHARS + 50)
    result = truncate_comment(text)
    assert len(result) == COMMENT_MAX_CHARS
