"""Generate comparison report PDF (Chinese-capable)."""

from __future__ import annotations

import io
import os
from datetime import datetime
from typing import Any
from urllib.parse import quote

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

_FONT_NAME = "ReportCN"
_FONT_BOLD = "ReportCN-Bold"
_FONTS_READY = False


def _register_fonts() -> None:
    global _FONTS_READY, _FONT_NAME, _FONT_BOLD
    if _FONTS_READY:
        return

    windir = os.environ.get("WINDIR", r"C:\Windows")
    fonts_dir = os.path.join(windir, "Fonts")
    regular_candidates = [
        (os.path.join(fonts_dir, "simhei.ttf"), False),
        (os.path.join(fonts_dir, "msyh.ttc"), True),
        (os.path.join(fonts_dir, "simsun.ttc"), True),
        (os.path.join(fonts_dir, "NotoSansSC-Regular.otf"), False),
    ]
    bold_candidates = [
        (os.path.join(fonts_dir, "msyhbd.ttc"), True),
        (os.path.join(fonts_dir, "simhei.ttf"), False),
        (os.path.join(fonts_dir, "msyh.ttc"), True),
    ]

    registered = False
    for path, is_ttc in regular_candidates:
        if not os.path.isfile(path):
            continue
        try:
            if is_ttc:
                pdfmetrics.registerFont(TTFont(_FONT_NAME, path, subfontIndex=0))
            else:
                pdfmetrics.registerFont(TTFont(_FONT_NAME, path))
            registered = True
            break
        except Exception:
            continue
    if not registered:
        _FONT_NAME = "Helvetica"
        _FONT_BOLD = "Helvetica-Bold"
        _FONTS_READY = True
        return

    bold_ok = False
    for path, is_ttc in bold_candidates:
        if not os.path.isfile(path):
            continue
        try:
            if is_ttc:
                pdfmetrics.registerFont(TTFont(_FONT_BOLD, path, subfontIndex=0))
            else:
                pdfmetrics.registerFont(TTFont(_FONT_BOLD, path))
            bold_ok = True
            break
        except Exception:
            continue
    if not bold_ok:
        _FONT_BOLD = _FONT_NAME
    _FONTS_READY = True


def _esc(text: Any) -> str:
    s = "" if text is None else str(text)
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _join_path(*parts: Any) -> str:
    items = [str(p).strip() for p in parts if p not in (None, "")]
    return " / ".join(items) if items else "-"


def _format_time(value: Any) -> str:
    if not value:
        return "-"
    text = str(value)
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(value)


def _alias_value(value: Any) -> str:
    text = "" if value is None else str(value)
    return "(空)" if text == "" else text


def _mode_label(mode: str | None, negate: bool | None = None) -> str:
    labels = {
        "include": "包含",
        "exclude": "不包含",
        "equals": "等于",
        "not_equals": "不等于",
    }
    if mode in labels:
        return labels[mode]
    return "不包含" if negate else "包含"


def _search_filter_logic_label(logic, fallback: str = "and") -> str:
    value = str(logic or fallback or "and").strip().lower()
    return "或" if value == "or" else "且"


def _search_filter_lines(record: dict, side: str) -> list[dict]:
    fallback_key = "sourceLogic" if side == "source" else "targetLogic"
    fallback = (record.get("searchFilters") or {}).get(fallback_key) or "and"
    lines = []
    for idx, item in enumerate((record.get("searchFilters") or {}).get(side) or []):
        field = item.get("field") or "全部字段"
        mode = _mode_label(item.get("mode"), item.get("negate"))
        keywords = " / ".join(str(k) for k in (item.get("keywords") or []))
        lines.append(
            {
                "text": f"{field} {mode} {keywords}",
                "logic": _search_filter_logic_label(item.get("logic"), fallback)
                if idx > 0
                else "且",
            }
        )
    return lines


def _join_search_filter_lines(record: dict, side: str) -> str:
    lines = _search_filter_lines(record, side)
    if not lines:
        return ""
    if len(lines) == 1:
        return lines[0]["text"]
    parts = [lines[0]["text"]]
    for item in lines[1:]:
        parts.append(item["logic"])
        parts.append(item["text"])
    return " ".join(parts)


def _build_styles():
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="CNTitle",
            fontName=_FONT_BOLD,
            fontSize=18,
            leading=24,
            alignment=TA_CENTER,
            spaceAfter=6,
            textColor=colors.HexColor("#1d2939"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="CNSub",
            fontName=_FONT_NAME,
            fontSize=10,
            leading=14,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#667085"),
            spaceAfter=16,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CNH2",
            fontName=_FONT_BOLD,
            fontSize=13,
            leading=18,
            spaceBefore=12,
            spaceAfter=8,
            textColor=colors.HexColor("#1d2939"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="CNH3",
            fontName=_FONT_BOLD,
            fontSize=11,
            leading=16,
            spaceBefore=8,
            spaceAfter=4,
            textColor=colors.HexColor("#344054"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="CNBody",
            fontName=_FONT_NAME,
            fontSize=10,
            leading=15,
            alignment=TA_LEFT,
            textColor=colors.HexColor("#344054"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="CNMuted",
            fontName=_FONT_NAME,
            fontSize=9,
            leading=13,
            textColor=colors.HexColor("#98a2b3"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="CNSmall",
            fontName=_FONT_NAME,
            fontSize=9,
            leading=13,
            textColor=colors.HexColor("#475467"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="CNOk",
            fontName=_FONT_BOLD,
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#039855"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="CNWarn",
            fontName=_FONT_NAME,
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#b54708"),
        )
    )
    return styles


def _kv_table(rows: list[tuple[str, str]], styles, col_widths=None) -> Table:
    data = [
        [Paragraph(_esc(k), styles["CNBody"]), Paragraph(_esc(v), styles["CNBody"])]
        for k, v in rows
    ]
    table = Table(data, colWidths=col_widths or [32 * mm, 140 * mm])
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), _FONT_NAME),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f8fafc")),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#344054")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e4eaf3")),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def _mapping_rows(report: dict) -> list[tuple[str, str, str]]:
    """Flatten field mappings for PDF: source, target, target table."""
    rows: list[tuple[str, str, str]] = []
    seen = set()
    for table in report.get("tables") or []:
        target_table = table.get("targetTable") or ""
        for col in table.get("columns") or []:
            source_table = col.get("sourceTable") or table.get("sourceTable") or ""
            source = col.get("source") or ""
            target = col.get("target") or ""
            if not source or not target:
                continue
            if " + " in str(source_table):
                continue
            left = f"{source_table}.{source}" if source_table else source
            right = f"{target_table}.{target}" if target_table else target
            key = f"{left}->{right}"
            if key in seen:
                continue
            seen.add(key)
            rows.append((left, right, target_table))
    return rows


def _result_paragraphs(record: dict, report: dict, styles) -> list:
    flow = []
    if not record.get("compared"):
        has_filtered = any(
            (t or {}).get("statsMode") == "filtered" for t in (report.get("tables") or [])
        )
        msg = (
            "当前报告按筛选条件仅统计当前对比表"
            if has_filtered
            else "未进行内容对比"
        )
        flow.append(Paragraph(_esc(msg), styles["CNMuted"]))
        return flow

    if record.get("statsMode") == "filtered":
        src = record.get("sourceTotal")
        tgt = record.get("targetTotal")
        if src == tgt:
            flow.append(
                Paragraph(
                    _esc(f"按当前筛选条件：源数据 {src} 条 = 目标数据 {tgt} 条"),
                    styles["CNOk"],
                )
            )
        else:
            flow.append(
                Paragraph(
                    _esc(f"按当前筛选条件：源数据 {src} 条，目标数据 {tgt} 条"),
                    styles["CNBody"],
                )
            )
            flow.append(
                Paragraph(
                    _esc(f"按较少一侧计一致数量：{record.get('matched')}"),
                    styles["CNSmall"],
                )
            )
        if record.get("leftOnly"):
            flow.append(
                Paragraph(_esc(f"源侧多出：{record.get('leftOnly')}"), styles["CNWarn"])
            )
        if record.get("rightOnly"):
            flow.append(
                Paragraph(_esc(f"目标侧多出：{record.get('rightOnly')}"), styles["CNWarn"])
            )
        return flow

    metrics = [
        ("源侧数量", record.get("sourceTotal")),
        ("目标侧数量", record.get("targetTotal")),
        ("一致数量", record.get("matched")),
        ("源侧不一致", record.get("leftOnly")),
        ("目标侧不一致", record.get("rightOnly")),
    ]
    data = [[Paragraph(_esc(k), styles["CNMuted"]) for k, _ in metrics]]
    data.append([Paragraph(_esc(v if v is not None else "-"), styles["CNBody"]) for _, v in metrics])
    table = Table(data, colWidths=[34 * mm] * 5)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f8fafc")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e4eaf3")),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    flow.append(table)
    return flow


def build_report_pdf(report: dict) -> bytes:
    _register_fonts()
    styles = _build_styles()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=str(report.get("taskName") or "对比报告"),
        author="数据库对比工具",
    )

    story = []
    story.append(Paragraph("对比报告", styles["CNTitle"]))
    story.append(
        Paragraph(
            f"生成时间：{_esc(_format_time(report.get('generatedAt')))}",
            styles["CNSub"],
        )
    )

    story.append(Paragraph("任务信息", styles["CNH2"]))
    source_label = _join_path(
        report.get("sourceLabel"), report.get("sourceDb"), report.get("sourceSchema")
    )
    target_label = _join_path(
        report.get("targetLabel"), report.get("targetDb"), report.get("targetSchema")
    )
    story.append(
        _kv_table(
            [
                ("任务名称", report.get("taskName") or "-"),
                ("源库", source_label),
                ("目标库", target_label),
            ],
            styles,
        )
    )

    mappings = _mapping_rows(report)
    if mappings:
        story.append(Paragraph("字段映射", styles["CNH2"]))
        header = [
            Paragraph("源字段", styles["CNBody"]),
            Paragraph("目标字段", styles["CNBody"]),
            Paragraph("目标表", styles["CNBody"]),
        ]
        data = [header]
        for left, right, target_table in mappings:
            data.append(
                [
                    Paragraph(_esc(left), styles["CNSmall"]),
                    Paragraph(_esc(right), styles["CNSmall"]),
                    Paragraph(_esc(target_table or "-"), styles["CNSmall"]),
                ]
            )
        table = Table(data, colWidths=[62 * mm, 62 * mm, 48 * mm], repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef4ff")),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e4eaf3")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [colors.white, colors.HexColor("#fbfcfe")],
                    ),
                ]
            )
        )
        story.append(table)

    story.append(Paragraph("对比明细", styles["CNH2"]))
    tables = report.get("tables") or []
    if not tables:
        story.append(Paragraph("暂无对比表", styles["CNMuted"]))
    else:
        for idx, record in enumerate(tables, start=1):
            if record.get("sourceTables") and len(record["sourceTables"]) > 1:
                pair_name = f"{' + '.join(record['sourceTables'])} ↔ {record.get('targetTable') or '-'}"
            else:
                pair_name = f"{record.get('sourceTable') or '-'} ↔ {record.get('targetTable') or '-'}"
            story.append(Paragraph(f"{idx}. {_esc(pair_name)}", styles["CNH3"]))

            compare_fields = record.get("compareFields") or []
            if compare_fields:
                labels = "、".join(f.get("label") or "" for f in compare_fields)
                mode = "模糊内容对比" if record.get("compareFuzzy") else "精确对比"
                story.append(
                    Paragraph(
                        f"<b>内容对比字段：</b>{_esc(labels)}（{_esc(mode)}）",
                        styles["CNSmall"],
                    )
                )
            else:
                story.append(
                    Paragraph("<b>内容对比字段：</b>未指定（按已映射字段）", styles["CNSmall"])
                )

            aliases = record.get("valueAliases") or []
            if aliases:
                alias_text = "；".join(
                    f"{a.get('sourceField')}:{_alias_value(a.get('sourceValue'))} = "
                    f"{a.get('targetField')}:{_alias_value(a.get('targetValue'))}"
                    for a in aliases
                )
                story.append(Paragraph(f"<b>对应关系：</b>{_esc(alias_text)}", styles["CNSmall"]))
            else:
                story.append(Paragraph("<b>对应关系：</b>无", styles["CNSmall"]))

            rules = record.get("extractMatchRules") or []
            if rules:
                rule_text = "；".join(
                    f"{r.get('sourceField')}[{r.get('sourcePositions')}] = "
                    f"{r.get('targetField')}[{r.get('targetPositions')}]"
                    for r in rules
                )
                story.append(
                    Paragraph(f"<b>提取匹配规则：</b>{_esc(rule_text)}", styles["CNSmall"])
                )
            else:
                story.append(Paragraph("<b>提取匹配规则：</b>无", styles["CNSmall"]))

            src_joined = _join_search_filter_lines(record, "source")
            tgt_joined = _join_search_filter_lines(record, "target")
            if src_joined or tgt_joined:
                parts = []
                if src_joined:
                    parts.append(f"源 · {src_joined}")
                if tgt_joined:
                    parts.append(f"目标 · {tgt_joined}")
                story.append(
                    Paragraph(
                        f"<b>模糊搜索条件：</b>{_esc('；'.join(parts))}",
                        styles["CNSmall"],
                    )
                )
            else:
                story.append(Paragraph("<b>模糊搜索条件：</b>无", styles["CNSmall"]))

            story.append(Spacer(1, 4))
            story.append(Paragraph("字段内容对比结果", styles["CNBody"]))
            story.extend(_result_paragraphs(record, report, styles))
            story.append(Spacer(1, 6))

    description = (report.get("description") or "").strip()
    story.append(Paragraph("对比报表说明", styles["CNH2"]))
    if description:
        for line in description.splitlines() or [description]:
            story.append(Paragraph(_esc(line) if line else "&nbsp;", styles["CNBody"]))
    else:
        story.append(Paragraph("无", styles["CNMuted"]))

    doc.build(story)
    return buffer.getvalue()


def pdf_filename(report: dict, task_id: int) -> str:
    name = (report.get("taskName") or f"task-{task_id}").strip() or f"task-{task_id}"
    safe = "".join(ch if ch not in '\\/:*?"<>|' else "_" for ch in name)[:80]
    return f"{safe}-对比报告.pdf"


def content_disposition(filename: str) -> str:
    """RFC 5987 Content-Disposition for Chinese filenames."""
    ascii_fallback = "compare-report.pdf"
    encoded = quote(filename)
    return f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{encoded}"
