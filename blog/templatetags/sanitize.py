import nh3
from django import template
from django.utils.safestring import mark_safe

register = template.Library()

ALLOWED_TAGS = {
    "a", "abbr", "acronym", "b", "blockquote", "br", "code", "em",
    "h1", "h2", "h3", "h4", "h5", "h6", "hr", "i", "img", "li",
    "ol", "p", "pre", "strong", "sub", "sup", "table", "tbody",
    "td", "th", "thead", "tr", "u", "ul", "figure", "figcaption",
    "div", "span",
}

# `style` is intentionally not allowed — inline CSS enables overlay/exfiltration
# attacks (full-viewport positioned elements, url() leaks). Tailwind classes are
# enough for CKEditor-generated markup.
ALLOWED_ATTRIBUTES = {
    "*": {"class"},
    "a": {"href", "title", "target"},
    "img": {"src", "alt", "width", "height", "loading"},
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan"},
}

ALLOWED_URL_SCHEMES = {"http", "https", "mailto"}


@register.filter(name="sanitize_html")
def sanitize_html(value):
    if not value:
        return ""
    cleaned = nh3.clean(
        value,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        url_schemes=ALLOWED_URL_SCHEMES,
        link_rel="noopener noreferrer",
    )
    # `cleaned` is the output of nh3.clean() above; mark_safe is the canonical
    # render path for already-sanitized HTML.
    return mark_safe(cleaned)  # nosec B703 B308
