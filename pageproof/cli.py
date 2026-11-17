"""`pageproof audit | demo | license`."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from . import audit as audit_mod, licensing, report
from .version import __version__

URL = "https://hymz.gumroad.com/l/pageproof"


def _require_pro(feature: str) -> None:
    print(f"{feature} is part of PageProof Pro — {URL}")
    raise SystemExit(1)


def demo_pdf(path: Path) -> Path:
    """Ship a five-page PDF with the mistakes that bounce at a printer."""
    from importlib import resources

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = resources.files("pageproof.data").joinpath("demo.pdf").read_bytes()
    path.write_bytes(payload)
    return path


def cmd_audit(args: argparse.Namespace) -> int:
    pro = licensing.is_pro()
    result = audit_mod.audit(args.input)

    print(f"\nPageProof {__version__} · {result['doc']['name']}")
    print(f"  score      {result['score']:.0f}/100  {result['verdict']}")
    print(f"  findings   {len(result['findings'])} "
          f"({result['severity'].get('high', 0)} high, "
          f"{result['severity'].get('medium', 0)} medium, "
          f"{result['severity'].get('low', 0)} low)")
    print(f"  pages      {result['pages']} · text pages {result['text_pages']} · "
          f"{result['page_size'][0] / 72:.2f}x{result['page_size'][1] / 72:.2f}in (page 1)")

    for row in audit_mod.summary_rows(result):
        print(f"  - {row['check']:<22} {row['count']:>3}  [{row['severity']}]")

    if pro and args.csv:
        out = Path(args.csv)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["severity", "check", "page", "target", "detail"])
            writer.writeheader()
            for f in result["findings"]:
                writer.writerow({k: f[k] for k in writer.fieldnames})
        print(f"\nfindings -> {out}")

    if args.report:
        if not pro:
            _require_pro("HTML report")
        out = Path(args.report)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report.build(result, pro=pro, version=__version__, top=args.top), "utf-8")
        print(f"report -> {out}")
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    pdf = demo_pdf(out / "demo.pdf")
    result = audit_mod.audit(pdf)

    print(f"{len(result['findings'])} findings · score {result['score']:.0f} · {result['verdict']}")
    for row in audit_mod.summary_rows(result):
        print(f"  - {row['check']}: {row['count']}")

    html = report.build(result, pro=licensing.is_pro(), version=__version__)
    (out / "pageproof-report.html").write_text(html, "utf-8")
    print(f"report -> {out / 'pageproof-report.html'} "
          f"({'Pro' if licensing.is_pro() else 'free tier'})")
    return 0


def cmd_license(args: argparse.Namespace) -> int:
    st = licensing.status()
    if st["valid"]:
        print(f"Pro license · {st['email']} · expires {st['expires'] or 'lifetime'}")
        print(f"source: {licensing.license_path()}")
    else:
        print(f"Free tier · {st['info']}")
        print(f"Pro: {URL}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="pageproof",
                                description="Find what bounces at the printer, before you send it.")
    p.add_argument("--version", action="version", version=f"pageproof {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    a = sub.add_parser("audit", help="audit a PDF")
    a.add_argument("-i", "--input", required=True)
    a.add_argument("--report", help="write an HTML report (Pro)")
    a.add_argument("--csv", help="write findings to CSV (Pro)")
    a.add_argument("--top", type=int, default=40)
    a.set_defaults(func=cmd_audit)

    d = sub.add_parser("demo", help="audit a bundled broken PDF")
    d.add_argument("-o", "--out", default="pageproof-demo")
    d.set_defaults(func=cmd_demo)

    l = sub.add_parser("license", help="license status")
    l.set_defaults(func=cmd_license)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
