# PageProof

Find what bounces at the printer before you send it.

PageProof reads a PDF's object tree and reports the problems that get files rejected — or
worse, printed wrong and paid for twice:

- pages that are not the same size as page 1
- a landscape page inside a portrait document
- text sitting inside the trim margin, or running off the page
- scanned pages with no text layer (invisible to search, screen readers and copy-paste)
- images placed at print resolution far below 150 DPI
- text set under 6pt
- five typefaces on a single page
- blank pages left in the file
- missing title and author metadata

It does **not** render or convert the PDF. No Ghostscript, no rasterising, no cloud upload.
It reads the same structure a preflight tool does, in about a second, offline.

## Install

```bash
pip install pageproof
```

Requires Python 3.9+.

## Use

```bash
pageproof audit -i brochure.pdf
```

```
PageProof 0.1.0 · spring_proof.pdf
  score      41/100  Will bounce at the printer
  findings   13 (2 high, 10 medium, 1 low)
  pages      5 · text pages 4 · 8.27x11.69in (page 1)
  - mixed page size        1  [high]
  - mixed orientation      1  [medium]
  - no text layer          1  [high]
  - blank page             1  [medium]
  - text in trim           3  [medium]
  - tiny text              1  [medium]
  - low dpi image          1  [medium]
  - font sprawl            1  [medium]
```

## Checks

| Check | What it catches | Severity |
|---|---|---|
| `mixed_page_size` | a page geometry that differs from page 1 by more than 2pt | high |
| `mixed_orientation` | landscape page in a portrait document, or the reverse | medium |
| `no_text_layer` | page is pictures only — a scan, needs OCR | high |
| `blank_page` | no text and no images | medium |
| `text_outside_page` | text crosses the page boundary | high |
| `text_in_trim` | text inside the 0.25in print safety margin | medium |
| `tiny_text` | characters under 6pt | medium |
| `low_dpi_image` | image placed under 150 DPI at its displayed size | medium |
| `font_sprawl` | more than four typefaces on one page | medium |
| `single_font_layer` | every page uses the same single typeface — usually a pasted text layer | low |
| `missing_metadata` | no metadata at all | low |
| `empty_metadata` | no title, or no author | low |

## Score

`100 * exp(-penalty / 120)`, where each check contributes `severity weight × min(count, cap)`.
High is 20, medium 8, low 2. 85+ is print-ready, 65–85 is fixable before it ships, below 65
will bounce at the printer.

## Try it without your own file

```bash
pageproof demo -o pageproof-demo
```

Writes a bundled five-page PDF with exactly these defects, audits it, and generates
`pageproof-report.html`. No network, no extra dependency.

## Free tier and Pro

The audit, the score and the per-check summary are free and stay free.

Pro adds the HTML report, CSV export for a print checklist, and a signed licence verified
offline (Ed25519, no server call). Sold at <https://hymz.gumroad.com>.

```bash
pageproof audit -i brochure.pdf --report prepress.html --csv findings.csv
pageproof license
```

## Limits, stated plainly

- Text-layer detection is a character count, not OCR. A page with an image and a handful of
  characters counts as text — check the flagged page before you trust it.
- Effective DPI is computed from the embedded pixel size against the placed size. Vector
  art and masks are not scored.
- Trim detection uses the page edge as the trim. If your printer supplies a separate TrimBox,
  subtract your real margin before reading the numbers.
- Emboldened/synthetic fonts, overprint and colour separation are out of scope — those
  remain a job for a real preflight tool.

## Built on

`pdfplumber` (MIT) for the PDF object layer. PageProof adds the checks, the scoring, the
report and the licence layer. See `NOTICE`.

## Licence

Business source: free to use, including commercially, on your own files. Redistribution or
resale of the source requires a commercial licence. `LICENSE` holds the full text.
