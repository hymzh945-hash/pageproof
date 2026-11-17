"""Read a PDF and report what breaks it at the printer, the client's inbox or the archive."""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Dict, List

import pdfplumber

SEVERITY_WEIGHT = {"high": 20, "medium": 8, "low": 2}
CHECK_CAP = {
    "mixed_page_size": 4, "mixed_orientation": 3, "no_text_layer": 4, "blank_page": 3,
    "text_outside_page": 4, "text_in_trim": 4, "tiny_text": 4, "low_dpi_image": 4,
    "font_sprawl": 3, "missing_metadata": 2, "empty_metadata": 2, "single_font_layer": 2,
}

# print safety: content closer than this to the edge risks being trimmed
TRIM_SAFE_IN = 0.25
MIN_PT = 6.0
MIN_IMAGE_DPI = 150
SIZE_TOLERANCE_PT = 2.0


def _finding(check: str, severity: str, page: int, target: str, detail: str) -> Dict:
    return {"check": check, "severity": severity, "page": page, "target": target,
            "detail": detail, "weight": SEVERITY_WEIGHT[severity]}


def _fmt_in(points: float) -> str:
    return f"{points / 72:.2f}in"


def load(path: str | Path) -> Dict:
    path = Path(path)
    if path.suffix.lower() != ".pdf":
        raise ValueError("only .pdf files are supported")

    pages = []
    with pdfplumber.open(str(path)) as pdf:
        meta = pdf.metadata or {}
        for index, page in enumerate(pdf.pages, start=1):
            chars = page.chars or []
            images = page.images or []
            fonts = sorted({c.get("fontname", "") for c in chars if c.get("fontname")})
            pages.append({
                "number": index,
                "width": float(page.width),
                "height": float(page.height),
                "chars": len(chars),
                "images": len(images),
                "fonts": fonts,
                "sizes": [round(float(c["size"]), 1) for c in chars if c.get("size")],
                "edges": {
                    "left": min((c["x0"] for c in chars), default=None),
                    "right": max((c["x1"] for c in chars), default=None),
                    "top": max((page.height - c["y0"] for c in chars), default=None),
                    "bottom": min((page.height - c["y1"] for c in chars), default=None),
                },
                "image_boxes": [
                    {
                        "width_pt": float(im["x1"]) - float(im["x0"]),
                        "height_pt": float(im["y1"]) - float(im["y0"]),
                        "src": tuple(im.get("srcsize") or ()),
                    }
                    for im in images
                ],
            })

    if not pages:
        raise ValueError("the PDF has no pages")

    return {
        "path": str(path),
        "name": path.name,
        "pages": pages,
        "metadata": {k: v for k, v in meta.items() if v not in (None, "")},
    }


def check_page_size(deck: Dict) -> List[Dict]:
    out = []
    first = deck["pages"][0]
    for page in deck["pages"]:
        if (abs(page["width"] - first["width"]) > SIZE_TOLERANCE_PT
                or abs(page["height"] - first["height"]) > SIZE_TOLERANCE_PT):
            out.append(_finding(
                "mixed_page_size", "high", page["number"], "page",
                f'{page["width"] / 72:.2f}x{page["height"] / 72:.2f}in against '
                f'{first["width"] / 72:.2f}x{first["height"] / 72:.2f}in on page 1'))
    return out


def check_orientation(deck: Dict) -> List[Dict]:
    out = []
    first_landscape = deck["pages"][0]["width"] > deck["pages"][0]["height"]
    for page in deck["pages"]:
        landscape = page["width"] > page["height"]
        if landscape != first_landscape:
            out.append(_finding(
                "mixed_orientation", "medium", page["number"], "page",
                f'{len(deck["pages"])} pages, page {page["number"]} flips from '
                f'{"landscape" if first_landscape else "portrait"} to '
                f'{"landscape" if landscape else "portrait"}'))
    return out


def check_text_layer(deck: Dict) -> List[Dict]:
    """A page with pictures and no characters is a scan: no search, no copy, no select."""
    out = []
    for page in deck["pages"]:
        if page["images"] and page["chars"] < 8:
            out.append(_finding("no_text_layer", "high", page["number"], "page",
                                f'{page["images"]} image(s) and {page["chars"]} characters — '
                                "scanned page, needs OCR before publishing"))
    return out


def check_blank(deck: Dict) -> List[Dict]:
    out = []
    for page in deck["pages"]:
        if page["chars"] == 0 and page["images"] == 0:
            out.append(_finding("blank_page", "medium", page["number"], "page",
                                "page has no text and no images"))
    return out


def check_edges(deck: Dict) -> List[Dict]:
    out = []
    for page in deck["pages"]:
        if not page["chars"]:
            continue
        edges = page["edges"]
        left, top = edges["left"] or 0, edges["top"] or 0
        right = page["width"] - (edges["right"] or page["width"])
        bottom = edges["bottom"] or 0
        for name, gap in (("left", left), ("top", top), ("right", right), ("bottom", bottom)):
            if gap < 0:
                out.append(_finding(
                    "text_outside_page", "high", page["number"], f"text at {name} edge",
                    f"text runs {-gap / 72:.2f}in past the page boundary"))
            elif gap / 72 < TRIM_SAFE_IN:
                out.append(_finding(
                    "text_in_trim", "medium", page["number"], f"text at {name} edge",
                    f'text sits {gap / 72:.2f}in from the {name} edge — inside a '
                    f'{TRIM_SAFE_IN}in print safety margin'))
    return out


def check_type_size(deck: Dict) -> List[Dict]:
    out = []
    for page in deck["pages"]:
        small = [s for s in page["sizes"] if s < MIN_PT]
        if small:
            out.append(_finding("tiny_text", "medium", page["number"], "page",
                                f"{len(small)} characters under {MIN_PT:g}pt "
                                f"(smallest {min(small):g}pt)"))
    return out


def check_images(deck: Dict) -> List[Dict]:
    out = []
    for page in deck["pages"]:
        for index, box in enumerate(page["image_boxes"], start=1):
            src = box["src"]
            if len(src) < 2 or not src[0] or not src[1]:
                continue
            width_in = box["width_pt"] / 72
            if width_in <= 0:
                continue
            dpi = int(round(src[0] / width_in))
            if dpi < MIN_IMAGE_DPI:
                out.append(_finding(
                    "low_dpi_image", "medium", page["number"], f"image {index}",
                    f"placed at {width_in:.2f}in wide from {src[0]}px — about {dpi} DPI, "
                    f"under {MIN_IMAGE_DPI} for print"))
    return out


def check_fonts(deck: Dict) -> List[Dict]:
    out = []
    for page in deck["pages"]:
        if len(page["fonts"]) > 4:
            out.append(_finding("font_sprawl", "medium", page["number"], "page",
                                f'{len(page["fonts"])} typefaces on one page: '
                                + ", ".join(page["fonts"][:5])))
    return out


def check_layers(deck: Dict) -> List[Dict]:
    """Every page carrying the exact same single font usually means a text layer pasted in."""
    names = {tuple(p["fonts"]) for p in deck["pages"] if p["chars"]}
    if len(names) == 1 and len(deck["pages"]) > 1:
        only = next(iter(names))
        if only:
            return [_finding("single_font_layer", "low", 1, "whole document",
                             f"every page uses the same {len(only)} typeface set — "
                             "likely an OCR or export layer, not the designer's file")]
    return []


def check_metadata(deck: Dict) -> List[Dict]:
    meta = deck["metadata"]
    if not meta:
        return [_finding("missing_metadata", "low", 1, "document",
                         "no document metadata at all — no title, no author, no producer")]
    missing = [k for k in ("Title", "Author") if not meta.get(k)]
    if missing:
        return [_finding("empty_metadata", "low", 1, "document",
                         "metadata has no " + " and no ".join(m.lower() for m in missing))]
    return []


CHECKS = [
    ("mixed_page_size", check_page_size),
    ("mixed_orientation", check_orientation),
    ("no_text_layer", check_text_layer),
    ("blank_page", check_blank),
    ("text_outside_page", check_edges),
    ("text_in_trim", check_edges),
    ("tiny_text", check_type_size),
    ("low_dpi_image", check_images),
    ("font_sprawl", check_fonts),
    ("single_font_layer", check_layers),
    ("missing_metadata", check_metadata),
    ("empty_metadata", check_metadata),
]


def audit(path: str | Path) -> Dict:
    deck = load(path)
    findings: List[Dict] = []
    for _name, fn in CHECKS:
        findings.extend(fn(deck))

    seen, unique = set(), []
    for f in findings:
        key = (f["check"], f["page"], f["target"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(f)

    penalty = 0.0
    for name, _fn in CHECKS:
        count = sum(1 for f in unique if f["check"] == name)
        if not count:
            continue
        penalty += min(count, CHECK_CAP.get(name, 3)) * SEVERITY_WEIGHT[
            next(f["severity"] for f in unique if f["check"] == name)]
    score = 100.0 * math.exp(-penalty / 120.0)

    if score >= 85:
        verdict, color = "Print-ready", "#34d399"
    elif score >= 65:
        verdict, color = "Fixable before it ships", "#fbbf24"
    else:
        verdict, color = "Will bounce at the printer", "#f87171"

    severity = {"high": 0, "medium": 0, "low": 0}
    for f in unique:
        severity[f["severity"]] += 1

    return {
        "doc": {
            "name": deck["name"],
            "pages": deck["pages"],
            "metadata": deck["metadata"],
        },
        "findings": unique,
        "score": score,
        "verdict": verdict,
        "verdict_color": color,
        "severity": severity,
        "pages": len(deck["pages"]),
        "page_size": (deck["pages"][0]["width"], deck["pages"][0]["height"]),
        "text_pages": sum(1 for p in deck["pages"] if p["chars"]),
        "counts": {name: sum(1 for f in unique if f["check"] == name) for name, _fn in CHECKS},
    }


def summary_rows(result: Dict) -> List[Dict]:
    rows = []
    for name, _fn in CHECKS:
        count = result["counts"].get(name, 0)
        if not count:
            continue
        severity = next((f["severity"] for f in result["findings"] if f["check"] == name), "low")
        rows.append({"check": name.replace("_", " "), "count": count, "severity": severity})
    return rows
