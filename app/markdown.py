import markdown as md
import bleach


# Разрешённые HTML-теги и атрибуты для пользовательского markdown
_ALLOWED_TAGS = [
    "p", "br", "h1", "h2", "h3", "h4", "h5", "h6",
    "strong", "em", "u", "s", "code", "pre", "blockquote",
    "ul", "ol", "li", "a", "hr",
]

_ALLOWED_ATTRIBUTES = {
    "a": ["href", "title", "target", "rel"],
}


def render_markdown(text: str | None) -> str:
    """Превратить markdown-пользователя в безопасный HTML."""
    if not text:
        return ""
    html = md.markdown(
        text,
        extensions=["nl2br", "fenced_code", "tables"],
        output_format="html",
    )
    return bleach.clean(
        html,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRIBUTES,
        strip=True,
    )
