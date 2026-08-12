"""Kind-specific SVG slide templates aligned with PPT Master quick-generate flat export."""

import base64
import html
import mimetypes
import re
from pathlib import Path

from iconography import ACCENT_COLORS, DEFAULT_ACCENT
from presentation_generator.export_scene import STAGE_SECTION_LABEL

CANVAS = "0 0 1280 720"
FONT = "Arial, Helvetica, sans-serif"
BG = "#0B1020"
BG_GRADIENT = "#121828"
MUTED = "#B8C4E0"
SUBTLE = "#6B7280"


def accent_hex(token: str) -> str:
    return ACCENT_COLORS.get(token or DEFAULT_ACCENT, ACCENT_COLORS[DEFAULT_ACCENT])


def _esc(text: str) -> str:
    return html.escape(str(text or ""))


def _words(text: str, limit: int) -> str:
    parts = re.split(r"\s+", str(text or "").strip())
    return " ".join(parts[:limit])


def _fit_title_size(text: str, max_width: int = 560, max_size: int = 58, min_size: int = 24) -> int:
    length = max(len(str(text or "")), 1)
    fitted = int(max_width / (length * 0.58))
    return max(min_size, min(max_size, fitted))


def _page_role(scene: dict) -> str:
    return scene.get("page_role") or {"hero": "cover", "quote": "ending"}.get(scene.get("kind", "hero"), "content")


def _slide_filename(index: int, scene: dict) -> str:
    stage = scene.get("presentation_stage", "slide")
    role = _page_role(scene)
    return f"{index:02d}_{role}_{stage}.svg"


def _chrome(content: dict, scene: dict, accent: str) -> tuple[str, str]:
    color = accent_hex(content.get("accent", accent))
    index = scene.get("slide_index", 1)
    total = scene.get("slide_total", index)
    stage = scene.get("presentation_stage", "other")
    section = _esc(content.get("eyebrow") or STAGE_SECTION_LABEL.get(stage, "Section"))
    top = f'<rect x="0" y="0" width="1280" height="4" fill="{color}"/>'
    footer = (
        f'<g id="footer" data-pptx-bounds="96 656 1088 40">'
        f'<text x="96" y="682" font-family="{FONT}" font-size="14" fill="{SUBTLE}">{section.upper()}</text>'
        f'<text x="1184" y="682" text-anchor="end" font-family="{FONT}" font-size="14" fill="{SUBTLE}">{index} / {total}</text>'
        f'</g>'
    )
    return top, footer


def _header_block(content: dict, accent: str, y_title: int = 148) -> str:
    eyebrow = _esc(content.get("eyebrow") or "")
    title = _esc(_words(content.get("title", "Untitled"), 8))
    subtitle = _esc(_words(content.get("subtitle", ""), 22))
    color = accent_hex(content.get("accent", accent))
    icon = _esc(str(content.get("icon") or "sparkles")[:2].upper())
    eyebrow_svg = (
        f'<text x="96" y="88" font-family="{FONT}" font-size="16" font-weight="600" fill="{color}" letter-spacing="2">{eyebrow.upper()}</text>'
        if eyebrow else ""
    )
    subtitle_svg = (
        f'<g id="subtitle" data-pptx-bounds="96 {y_title + 32} 900 72"><text x="96" y="{y_title + 56}" font-family="{FONT}" font-size="24" fill="{MUTED}">{subtitle}</text></g>'
        if subtitle else ""
    )
    return f'''{eyebrow_svg}
<circle cx="1120" cy="96" r="34" fill="{color}" opacity="0.16"/>
<text x="1120" y="104" text-anchor="middle" font-family="{FONT}" font-size="15" font-weight="700" fill="{color}">{icon}</text>
<g id="title" data-pptx-bounds="96 {y_title - 48} 900 96"><text x="96" y="{y_title}" font-family="{FONT}" font-size="52" font-weight="700" fill="#FFFFFF">{title}</text></g>
{subtitle_svg}'''


def _cards_block(content: dict, accent: str, ordered: bool = False) -> str:
    color = accent_hex(content.get("accent", accent))
    items = content.get("card_items") or [{"title": c, "body": "", "icon": "•"} for c in content.get("cards", [])]
    parts = []
    for index, card in enumerate(items[:4]):
        col = index % 2
        row = index // 2
        x = 96 + col * 560
        y = 292 + row * 176
        title = _esc(_words(card.get("title", f"Point {index + 1}"), 5))
        body = _esc(_words(card.get("body", ""), 16))
        marker = str(index + 1) if ordered else "•"
        parts.append(
            f'<g id="card-{index + 1}" data-pptx-bounds="{x} {y} 520 156">'
            f'<rect x="{x}" y="{y}" width="520" height="156" rx="14" fill="#141C33" stroke="{color}" stroke-width="2"/>'
            f'<rect x="{x + 20}" y="{y + 18}" width="28" height="28" rx="8" fill="{color}" opacity="0.18"/>'
            f'<text x="{x + 34}" y="{y + 38}" text-anchor="middle" font-family="{FONT}" font-size="14" font-weight="700" fill="{color}">{marker}</text>'
            f'<text x="{x + 58}" y="{y + 38}" font-family="{FONT}" font-size="20" font-weight="700" fill="#FFFFFF">{title}</text>'
            f'<text x="{x + 24}" y="{y + 72}" font-family="{FONT}" font-size="18" fill="{MUTED}">{body}</text>'
            f'</g>'
        )
    return "".join(parts)


def _pipeline_block(content: dict, accent: str) -> str:
    color = accent_hex(content.get("accent", accent))
    items = content.get("card_items") or [{"title": c, "body": "", "icon": "arrow-right"} for c in content.get("cards", [])]
    parts = []
    for index, card in enumerate(items[:5]):
        y = 300 + index * 68
        title = _esc(_words(card.get("title", f"Step {index + 1}"), 6))
        body = _esc(_words(card.get("body", ""), 14))
        parts.append(
            f'<g id="step-{index + 1}" data-pptx-bounds="96 {y - 8} 1088 56">'
            f'<circle cx="118" cy="{y + 20}" r="18" fill="{color}"/>'
            f'<text x="118" y="{y + 26}" text-anchor="middle" font-family="{FONT}" font-size="14" font-weight="700" fill="#0B1020">{index + 1}</text>'
            f'<text x="156" y="{y + 18}" font-family="{FONT}" font-size="22" font-weight="700" fill="#FFFFFF">{title}</text>'
            f'<text x="156" y="{y + 44}" font-family="{FONT}" font-size="18" fill="{MUTED}">{body}</text>'
            f'</g>'
        )
        if index < min(len(items), 5) - 1:
            parts.append(f'<line x1="118" y1="{y + 38}" x2="118" y2="{y + 58}" stroke="{color}" stroke-width="2" opacity="0.45"/>')
    return "".join(parts)


def _metric_block(content: dict, accent: str) -> str:
    color = accent_hex(content.get("accent", accent))
    metrics = content.get("metrics") or [{"value": "—", "label": "KEY METRIC"}]
    parts = []
    count = min(len(metrics), 3)
    span = 1088 // max(count, 1)
    for index, metric in enumerate(metrics[:3]):
        cx = 96 + span * index + span // 2
        value = _esc(str(metric.get("value", "—")))
        label = _esc(_words(metric.get("label", "METRIC"), 4).upper())
        parts.append(
            f'<g id="metric-{index + 1}" data-pptx-bounds="{cx - 120} 300 240 220">'
            f'<circle cx="{cx}" cy="390" r="72" fill="none" stroke="{color}" stroke-width="10" opacity="0.95"/>'
            f'<text x="{cx}" y="402" text-anchor="middle" font-family="{FONT}" font-size="42" font-weight="700" fill="#FFFFFF">{value}</text>'
            f'<text x="{cx}" y="490" text-anchor="middle" font-family="{FONT}" font-size="16" font-weight="600" letter-spacing="1" fill="{MUTED}">{label}</text>'
            f'</g>'
        )
    return "".join(parts)


def _quote_block(content: dict, accent: str) -> str:
    color = accent_hex(content.get("accent", accent))
    quote = _esc(_words(content.get("title") or content.get("primary_idea") or "", 20))
    attribution = _esc(_words(content.get("subtitle") or "", 10))
    return (
        f'<g id="quote" data-pptx-bounds="120 250 1040 220">'
        f'<rect x="120" y="250" width="8" height="180" fill="{color}"/>'
        f'<text x="160" y="330" font-family="{FONT}" font-size="40" font-weight="700" font-style="italic" fill="#FFFFFF">{quote}</text>'
        f'<text x="160" y="390" font-family="{FONT}" font-size="22" fill="{MUTED}">— {attribution}</text>'
        f'</g>'
    )


def _editorial_header(content: dict, accent: str, kind: str) -> str:
    """Left-column header for all editorial slide kinds."""
    eyebrow = _esc(content.get("eyebrow") or "")
    title = _esc(_words(content.get("title", "Untitled"), 8))
    subtitle = _esc(_words(content.get("subtitle", ""), 22))
    color = accent_hex(content.get("accent", accent))
    title_size = 58 if kind == "hero" else 38
    title_y = 240 if kind == "hero" else 168
    eyebrow_svg = (
        f'<text x="96" y="108" font-family="{FONT}" font-size="14" font-weight="600" fill="{color}" letter-spacing="2">{eyebrow.upper()}</text>'
        if eyebrow else ""
    )
    subtitle_y = 360 if kind == "hero" else 206
    subtitle_svg = (
        f'<text x="96" y="{subtitle_y}" font-family="{FONT}" font-size="22" fill="#4B5563">{subtitle}</text>'
        if subtitle else ""
    )
    return f'''{eyebrow_svg}
<g id="title" data-pptx-bounds="96 {title_y - 72} 580 120"><text x="96" y="{title_y}" font-family="{FONT}" font-size="{title_size}" font-weight="700" fill="#111827">{title}</text></g>
{subtitle_svg}'''


def _cards_block_editorial(content: dict, accent: str) -> str:
    color = accent_hex(content.get("accent", accent))
    items = content.get("card_items") or [{"title": c, "body": "", "icon": "•"} for c in content.get("cards", [])]
    parts = []
    for index, card in enumerate(items[:4]):
        col = index % 2
        row = index // 2
        x = 96 + col * 292
        y = 236 + row * 118
        title = _esc(_words(card.get("title", f"Point {index + 1}"), 5))
        body = _esc(_words(card.get("body", ""), 12))
        parts.append(
            f'<g id="card-{index + 1}" data-pptx-bounds="{x} {y} 276 104">'
            f'<rect x="{x}" y="{y}" width="276" height="104" rx="12" fill="#FFFFFF" stroke="#E5E7EB" stroke-width="1.5"/>'
            f'<rect x="{x}" y="{y}" width="276" height="4" rx="2" fill="{color}"/>'
            f'<text x="{x + 14}" y="{y + 30}" font-family="{FONT}" font-size="16" font-weight="700" fill="#111827">{title}</text>'
            f'<text x="{x + 14}" y="{y + 54}" font-family="{FONT}" font-size="14" fill="#6B7280">{body}</text>'
            f'</g>'
        )
    return "".join(parts)


def _pipeline_block_editorial(content: dict, accent: str) -> str:
    color = accent_hex(content.get("accent", accent))
    items = content.get("card_items") or [{"title": c, "body": "", "icon": "arrow-right"} for c in content.get("cards", [])]
    parts = []
    for index, card in enumerate(items[:5]):
        y = 236 + index * 56
        title = _esc(_words(card.get("title", f"Step {index + 1}"), 6))
        body = _esc(_words(card.get("body", ""), 14))
        parts.append(
            f'<g id="step-{index + 1}" data-pptx-bounds="96 {y - 4} 580 48">'
            f'<circle cx="112" cy="{y + 16}" r="14" fill="{color}"/>'
            f'<text x="112" y="{y + 21}" text-anchor="middle" font-family="{FONT}" font-size="12" font-weight="700" fill="#FFFFFF">{index + 1}</text>'
            f'<text x="136" y="{y + 14}" font-family="{FONT}" font-size="17" font-weight="700" fill="#111827">{title}</text>'
            f'<text x="136" y="{y + 34}" font-family="{FONT}" font-size="14" fill="#6B7280">{body}</text>'
            f'</g>'
        )
    return "".join(parts)


def _metric_block_editorial(content: dict, accent: str) -> str:
    color = accent_hex(content.get("accent", accent))
    metrics = content.get("metrics") or [{"value": "—", "label": "KEY METRIC"}]
    parts = []
    for index, metric in enumerate(metrics[:3]):
        y = 250 + index * 110
        value = _esc(str(metric.get("value", "—")))
        label = _esc(_words(metric.get("label", "METRIC"), 4).upper())
        parts.append(
            f'<g id="metric-{index + 1}" data-pptx-bounds="96 {y} 320 90">'
            f'<text x="96" y="{y + 36}" font-family="{FONT}" font-size="40" font-weight="700" fill="{color}">{value}</text>'
            f'<text x="96" y="{y + 62}" font-family="{FONT}" font-size="14" font-weight="600" letter-spacing="1" fill="#6B7280">{label}</text>'
            f'</g>'
        )
    return "".join(parts)


def _quote_block_editorial(content: dict, accent: str) -> str:
    color = accent_hex(content.get("accent", accent))
    quote = _esc(_words(content.get("title") or content.get("primary_idea") or "", 16))
    attribution = _esc(_words(content.get("subtitle") or "", 10))
    return (
        f'<g id="quote" data-pptx-bounds="96 250 580 200">'
        f'<rect x="96" y="250" width="6" height="160" fill="{color}"/>'
        f'<text x="118" y="310" font-family="{FONT}" font-size="30" font-weight="700" font-style="italic" fill="#111827">{quote}</text>'
        f'<text x="118" y="360" font-family="{FONT}" font-size="18" fill="#6B7280">— {attribution}</text>'
        f'</g>'
    )


def _hero_header_left(content: dict, accent: str) -> str:
    """ZeroPrep-style hero copy column — title and subtitle on the left."""
    eyebrow = _esc(content.get("eyebrow") or "")
    raw_title = _words(content.get("title", "Untitled"), 8)
    title = _esc(raw_title)
    subtitle = _esc(_words(content.get("subtitle", ""), 22))
    color = accent_hex(content.get("accent", accent))
    title_size = _fit_title_size(raw_title, max_width=560)
    eyebrow_svg = (
        f'<text x="96" y="120" font-family="{FONT}" font-size="16" font-weight="600" fill="{color}" letter-spacing="2">{eyebrow.upper()}</text>'
        if eyebrow else ""
    )
    subtitle_svg = (
        f'<text x="96" y="360" font-family="{FONT}" font-size="26" fill="#4B5563">{subtitle}</text>'
        if subtitle else ""
    )
    return f'''{eyebrow_svg}
<g id="title" data-pptx-bounds="96 160 560 180"><text x="96" y="240" font-family="{FONT}" font-size="{title_size}" font-weight="700" fill="#111827">{title}</text></g>
{subtitle_svg}'''


def _header_compact(content: dict, accent: str, max_width: int = 1088) -> str:
    eyebrow = _esc(content.get("eyebrow") or "")
    raw_title = _words(content.get("title", "Untitled"), 10)
    title = _esc(raw_title)
    subtitle = _esc(_words(content.get("subtitle", ""), 24))
    color = accent_hex(content.get("accent", accent))
    title_size = _fit_title_size(raw_title, max_width=max_width - 96, max_size=40, min_size=22)
    eyebrow_svg = (
        f'<text x="96" y="108" font-family="{FONT}" font-size="14" font-weight="600" fill="{color}" letter-spacing="2">{eyebrow.upper()}</text>'
        if eyebrow else ""
    )
    subtitle_svg = (
        f'<text x="96" y="196" font-family="{FONT}" font-size="22" fill="#4B5563">{subtitle}</text>'
        if subtitle else ""
    )
    return f'''{eyebrow_svg}
<g id="title" data-pptx-bounds="96 120 {max_width} 80"><text x="96" y="168" font-family="{FONT}" font-size="{title_size}" font-weight="700" fill="#111827">{title}</text></g>
{subtitle_svg}'''


def _cards_block_full_width(content: dict, accent: str) -> str:
    color = accent_hex(content.get("accent", accent))
    items = content.get("card_items") or [{"title": c, "body": "", "icon": "•"} for c in content.get("cards", [])]
    parts = []
    cols = 2 if len(items) <= 4 else 3
    card_w = 520 if cols == 2 else 340
    gap_x = 560 if cols == 2 else 368
    for index, card in enumerate(items[:6]):
        col = index % cols
        row = index // cols
        x = 96 + col * gap_x
        y = 240 + row * 168
        title = _esc(_words(card.get("title", f"Point {index + 1}"), 5))
        body = _esc(_words(card.get("body", ""), 14))
        parts.append(
            f'<g id="card-{index + 1}" data-pptx-bounds="{x} {y} {card_w} 148">'
            f'<rect x="{x}" y="{y}" width="{card_w}" height="148" rx="14" fill="#FFFFFF" stroke="#E5E7EB" stroke-width="1.5"/>'
            f'<rect x="{x}" y="{y}" width="{card_w}" height="5" rx="2" fill="{color}"/>'
            f'<text x="{x + 18}" y="{y + 36}" font-family="{FONT}" font-size="18" font-weight="700" fill="#111827">{title}</text>'
            f'<text x="{x + 18}" y="{y + 64}" font-family="{FONT}" font-size="15" fill="#6B7280">{body}</text>'
            f'</g>'
        )
    return "".join(parts)


def _cards_block_with_small_visual(content: dict, accent: str) -> str:
    color = accent_hex(content.get("accent", accent))
    items = content.get("card_items") or [{"title": c, "body": "", "icon": "•"} for c in content.get("cards", [])]
    parts = []
    for index, card in enumerate(items[:3]):
        col = index % 2
        row = index // 2
        x = 96 + col * 400
        y = 240 + row * 148
        title = _esc(_words(card.get("title", f"Point {index + 1}"), 5))
        body = _esc(_words(card.get("body", ""), 12))
        parts.append(
            f'<g id="card-{index + 1}" data-pptx-bounds="{x} {y} 380 132">'
            f'<rect x="{x}" y="{y}" width="380" height="132" rx="12" fill="#FFFFFF" stroke="#E5E7EB" stroke-width="1.5"/>'
            f'<rect x="{x}" y="{y}" width="380" height="4" rx="2" fill="{color}"/>'
            f'<text x="{x + 14}" y="{y + 32}" font-family="{FONT}" font-size="17" font-weight="700" fill="#111827">{title}</text>'
            f'<text x="{x + 14}" y="{y + 56}" font-family="{FONT}" font-size="14" fill="#6B7280">{body}</text>'
            f'</g>'
        )
    return "".join(parts)


def _architecture_diagram_block(content: dict, accent: str) -> str:
    color = accent_hex(content.get("accent", accent))
    items = content.get("card_items") or []
    labels = [item.get("title", "") for item in items[:6] if item.get("title")]
    if not labels:
        labels = ["Browser", "Realtime", "Orchestrator", "State Manager", "PPT Generator", "PPTX"]
    parts = []
    y = 230
    for index, label in enumerate(labels):
        text = _esc(_words(label, 4))
        box_y = y + index * 68
        parts.append(
            f'<g id="arch-node-{index + 1}" data-pptx-bounds="320 {box_y - 8} 640 52">'
            f'<rect x="320" y="{box_y}" width="640" height="48" rx="12" fill="#FFFFFF" stroke="{color}" stroke-width="2"/>'
            f'<text x="640" y="{box_y + 30}" text-anchor="middle" font-family="{FONT}" font-size="20" font-weight="700" fill="#111827">{text}</text>'
            f'</g>'
        )
        if index < len(labels) - 1:
            parts.append(
                f'<line x1="640" y1="{box_y + 48}" x2="640" y2="{box_y + 68}" stroke="{color}" stroke-width="2" marker-end="url(#arrow)"/>'
            )
    return (
        '<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">'
        f'<path d="M0,0 L6,3 L0,6 Z" fill="{color}"/></marker></defs>'
        + "".join(parts)
    )


def _pipeline_horizontal_block(content: dict, accent: str) -> str:
    color = accent_hex(content.get("accent", accent))
    items = content.get("card_items") or [{"title": c, "body": "", "icon": "arrow-right"} for c in content.get("cards", [])]
    if not items:
        items = [{"title": "Input"}, {"title": "Plan"}, {"title": "Build"}, {"title": "Export"}]
    count = min(len(items), 5)
    span = 960 // max(count, 1)
    parts = ['<defs><marker id="pipe-arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">'
             f'<path d="M0,0 L6,3 L0,6 Z" fill="{color}"/></marker></defs>']
    y = 360
    for index, card in enumerate(items[:count]):
        cx = 160 + span * index
        title = _esc(_words(card.get("title", f"Step {index + 1}"), 4))
        parts.append(
            f'<g id="pipe-{index + 1}" data-pptx-bounds="{cx - 70} {y - 20} 140 100">'
            f'<circle cx="{cx}" cy="{y}" r="34" fill="{color}"/>'
            f'<text x="{cx}" y="{y + 6}" text-anchor="middle" font-family="{FONT}" font-size="14" font-weight="700" fill="#FFFFFF">{index + 1}</text>'
            f'<text x="{cx}" y="{y + 56}" text-anchor="middle" font-family="{FONT}" font-size="16" font-weight="700" fill="#111827">{title}</text>'
            f'</g>'
        )
        if index < count - 1:
            x1 = cx + 38
            x2 = 160 + span * (index + 1) - 38
            parts.append(f'<line x1="{x1}" y1="{y}" x2="{x2}" y2="{y}" stroke="{color}" stroke-width="3" marker-end="url(#pipe-arrow)"/>')
    return "".join(parts)


def _metrics_dashboard_block(content: dict, accent: str) -> str:
    color = accent_hex(content.get("accent", accent))
    metrics = content.get("metrics") or [{"value": "—", "label": "METRIC"}]
    parts = []
    count = min(len(metrics), 4)
    span = 1088 // max(count, 1)
    for index, metric in enumerate(metrics[:4]):
        cx = 96 + span * index + span // 2
        value = _esc(str(metric.get("value", "—")))
        label = _esc(_words(metric.get("label", "METRIC"), 4).upper())
        parts.append(
            f'<g id="metric-{index + 1}" data-pptx-bounds="{cx - 120} 280 240 200">'
            f'<rect x="{cx - 110}" y="280" width="220" height="180" rx="16" fill="#FFFFFF" stroke="#E5E7EB" stroke-width="1.5"/>'
            f'<text x="{cx}" y="370" text-anchor="middle" font-family="{FONT}" font-size="48" font-weight="700" fill="{color}">{value}</text>'
            f'<text x="{cx}" y="410" text-anchor="middle" font-family="{FONT}" font-size="14" font-weight="600" letter-spacing="1" fill="#6B7280">{label}</text>'
            f'</g>'
        )
    return "".join(parts)


def _quote_typography_block(content: dict, accent: str) -> str:
    color = accent_hex(content.get("accent", accent))
    quote = _esc(_words(content.get("title") or content.get("primary_idea") or "", 18))
    attribution = _esc(_words(content.get("subtitle") or "", 10))
    return (
        f'<g id="quote" data-pptx-bounds="180 220 920 260">'
        f'<text x="640" y="320" text-anchor="middle" font-family="{FONT}" font-size="44" font-weight="700" font-style="italic" fill="#111827">{quote}</text>'
        f'<text x="640" y="390" text-anchor="middle" font-family="{FONT}" font-size="22" fill="#6B7280">— {attribution}</text>'
        f'<rect x="480" y="410" width="320" height="4" rx="2" fill="{color}" opacity="0.5"/>'
        f'</g>'
    )


def _hero_focus_copy(content: dict, accent: str) -> str:
    eyebrow = _esc(content.get("eyebrow") or "")
    title = _esc(_words(content.get("title", "Untitled"), 8))
    subtitle = _esc(_words(content.get("subtitle", ""), 22))
    color = accent_hex(content.get("accent", accent))
    eyebrow_svg = (
        f'<text x="96" y="540" font-family="{FONT}" font-size="14" font-weight="600" fill="{color}" letter-spacing="2">{eyebrow.upper()}</text>'
        if eyebrow else ""
    )
    subtitle_svg = (
        f'<text x="96" y="610" font-family="{FONT}" font-size="24" fill="#4B5563">{subtitle}</text>'
        if subtitle else ""
    )
    return f'''{eyebrow_svg}
<g id="title" data-pptx-bounds="96 560 1088 80"><text x="96" y="580" font-family="{FONT}" font-size="44" font-weight="700" fill="#111827">{title}</text></g>
{subtitle_svg}'''


def _visual_placeholder(bounds, accent: str) -> str:
    from presentation_generator.visual_strategy import VisualBounds

    if isinstance(bounds, VisualBounds):
        b = bounds
    else:
        b = bounds
    color = accent_hex(accent)
    return (
        f'<g id="visual-placeholder" data-pptx-bounds="{b.x} {b.y} {b.width} {b.height}">'
        f'<rect x="{b.x}" y="{b.y}" width="{b.width}" height="{b.height}" rx="16" fill="#EEF2F7" stroke="#D1D5DB" stroke-width="2"/>'
        f'<circle cx="{b.x + b.width // 2}" cy="{b.y + b.height // 2}" r="36" fill="{color}" opacity="0.14"/>'
        f'</g>'
    )


def _visual_image_block(image_path: Path | str, bounds, clip_id: str) -> str:
    from presentation_generator.visual_strategy import VisualBounds

    path = Path(image_path)
    if not path.is_file():
        return ""
    b = bounds if isinstance(bounds, VisualBounds) else bounds
    try:
        href = _image_data_uri(path)
    except OSError:
        return ""
    fit = "xMidYMid slice" if b.fit == "cover" else "xMidYMid meet"
    pad = 2
    return (
        f'<g id="slide-visual" data-pptx-bounds="{b.x} {b.y} {b.width} {b.height}">'
        f'<rect x="{b.x}" y="{b.y}" width="{b.width}" height="{b.height}" rx="16" fill="#EEF2F7" stroke="#D1D5DB" stroke-width="1.5"/>'
        f'<defs><clipPath id="{clip_id}"><rect x="{b.x + pad}" y="{b.y + pad}" width="{b.width - pad * 2}" height="{b.height - pad * 2}" rx="14"/></clipPath></defs>'
        f'<image id="gemini-slide-visual" href="{href}" x="{b.x + pad}" y="{b.y + pad}" width="{b.width - pad * 2}" height="{b.height - pad * 2}" '
        f'preserveAspectRatio="{fit}" clip-path="url(#{clip_id})" data-pptx-role="hero-image"/>'
        f'</g>'
    )


def _image_data_uri(image_path: Path) -> str:
    mime = mimetypes.guess_type(str(image_path))[0] or "image/png"
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _background_image_block(image_path: Path | str | None) -> str:
    if not image_path:
        return ""
    path = Path(image_path)
    if not path.is_file():
        return ""
    try:
        href = _image_data_uri(path)
    except OSError:
        return ""
    return (
        f'<image id="gemini-background" href="{href}" x="0" y="0" width="1280" height="720" '
        f'preserveAspectRatio="xMidYMid slice" data-pptx-role="background-image"/>'
        f'<rect width="1280" height="720" fill="{BG}" opacity="0.68"/>'
    )


def build_scene_svg(scene: dict, background_image: Path | str | None = None) -> str:
    from presentation_generator.visual_strategy import resolve_visual_plan

    content = scene.get("content", {})
    accent = content.get("accent", DEFAULT_ACCENT)
    page_role = _page_role(scene)
    chrome_top, chrome_footer = _chrome(content, scene, accent)
    plan = resolve_visual_plan(scene)
    clip_id = f"clip-{_esc(scene.get('id', 'slide')).replace(' ', '')[:20]}"

    strategy = plan.strategy
    if strategy == "quote_typography":
        body = _quote_typography_block(content, accent)
        header = _header_compact(content, accent)
    elif strategy == "architecture_diagram":
        header = _header_compact(content, accent)
        body = _architecture_diagram_block(content, accent)
    elif strategy == "pipeline_horizontal":
        header = _header_compact(content, accent)
        body = _pipeline_horizontal_block(content, accent)
    elif strategy == "metrics_dashboard":
        header = _header_compact(content, accent)
        body = _metrics_dashboard_block(content, accent)
    elif strategy == "cards_full_width":
        header = _header_compact(content, accent)
        body = _cards_block_full_width(content, accent)
    elif strategy == "cards_with_small_visual":
        header = _header_compact(content, accent, max_width=780)
        body = _cards_block_with_small_visual(content, accent)
    elif strategy == "hero_visual_focus":
        body = _hero_focus_copy(content, accent)
        header = ""
    else:
        header = _hero_header_left(content, accent)
        body = ""

    visual = ""
    if plan.visual_bounds and background_image:
        visual = _visual_image_block(background_image, plan.visual_bounds, clip_id)
    elif plan.visual_bounds and plan.needs_gemini_image:
        visual = _visual_placeholder(plan.visual_bounds, accent)

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="{CANVAS}" data-pptx-page-role="{page_role}" data-visual-strategy="{strategy}">
<rect id="background" width="1280" height="720" fill="#FAFAFA" data-pptx-role="background"/>
{chrome_top}
<g id="content" data-pptx-bounds="96 72 1088 560" font-family="{FONT}" fill="#111827">{header}{body}{visual}</g>
{chrome_footer}
</svg>'''
