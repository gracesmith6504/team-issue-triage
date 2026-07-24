BODY_MAX_CHARS = 3000
COMMENT_MAX_CHARS = 500


def truncate_body(text: str | None) -> str:
    if not text:
        return "(no description provided)"
    return text[:BODY_MAX_CHARS]


def truncate_comment(text: str | None) -> str:
    if not text:
        return ""
    return text[:COMMENT_MAX_CHARS]
