#!/usr/bin/env python3
"""Check published bounds, native downloads and generated default-view tables.

Run after the static build. This is a consistency check, not a threshold fit.
Use --self-test to exercise the failure cases without reading the catalogue.
"""
from __future__ import annotations

import argparse
import copy
import csv
import json
import math
import tempfile
from decimal import Decimal, ROUND_HALF_UP
from html.parser import HTMLParser
from pathlib import Path

PRIMARY = {
    "Genome_Size", "GC_Content", "Total_Coding_Sequences",
    "Completeness_Specific", "Contamination", "N50", "no_of_contigs",
}
EXTERNAL = {"Genome_Size", "N50", "no_of_contigs"}
LOWER_ONLY = {"N50", "Completeness_Specific"}
UPPER_ONLY = {"no_of_contigs", "Contamination"}
FIELDS = ("final_lower", "warn_lower", "warn_upper", "final_upper")
ALIASES = {"Completeness": "Completeness_Specific", "number": "no_of_contigs"}
HEADERS = ["Metric", "Fail below", "Warn below", "Warn above", "Fail above"]


def same(a, b):
    return a is None and b is None or (
        isinstance(a, (int, float)) and not isinstance(a, bool)
        and isinstance(b, (int, float)) and not isinstance(b, bool)
        and math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-9)
    )


def number(value):
    if value is None or str(value).strip() in ("", "-", "–"):
        return None
    result = float(str(value).replace(",", ""))
    if not math.isfinite(result):
        raise ValueError("nonfinite number")
    return result


def operational_values(row):
    return [
        row.get("final_lower"),
        row.get("warn_lower") if row.get("final_lower") is not None else None,
        row.get("warn_upper") if row.get("final_upper") is not None else None,
        row.get("final_upper"),
    ]


def validate_row(row, external=False):
    errors = []
    metric = row.get("metric")
    for key in (*FIELDS, "lower", "upper"):
        value = row.get(key)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            errors.append(f"{key} is not a finite number")
        elif value < 0 or metric == "GC_Content" and value > 100:
            errors.append(f"{key} is outside its numeric domain")
        elif metric in {"Genome_Size", "N50", "no_of_contigs", "Total_Coding_Sequences"} and value == 0:
            errors.append(f"{key} must be positive for a size/count metric")
    if errors:
        return errors
    for legacy, canonical in [("lower", "final_lower"), ("upper", "final_upper")]:
        if not same(row.get(legacy), row.get(canonical)):
            errors.append(f"{legacy} differs from {canonical}")
    for lo, hi in [("final_lower", "final_upper"), ("warn_lower", "warn_upper")]:
        if row.get(lo) is not None and row.get(hi) is not None and row[lo] > row[hi]:
            errors.append(f"{lo} exceeds {hi}")
    if metric == "longest":
        if row.get("final_lower") is not None or row.get("final_upper") is not None:
            errors.append("descriptive longest-contig row has a failure bound")
        return errors
    if metric in LOWER_ONLY:
        if row.get("final_lower") is None or row.get("final_upper") is not None:
            errors.append("expected a lower failure bound only")
    elif metric in UPPER_ONLY:
        if row.get("final_upper") is None or row.get("final_lower") is not None:
            errors.append("expected an upper failure bound only")
    elif row.get("final_lower") is None or row.get("final_upper") is None:
        errors.append("expected both failure bounds")
    if not external:
        for fail, warn in [("final_lower", "warn_lower"), ("final_upper", "warn_upper")]:
            if row.get(fail) is not None and row.get(warn) is None:
                errors.append(f"missing operational {warn}")
        lo, wl, wu, hi = operational_values(row)
        if lo is not None and wl is not None and wl < lo:
            errors.append("warning lower is outside failure lower")
        if hi is not None and wu is not None and wu > hi:
            errors.append("warning upper is outside failure upper")
        if all(v is not None for v in (lo, wl, wu, hi)) and max(lo, wl) > min(hi, wu):
            errors.append("operational PASS interval is empty")
    elif row.get("warn_lower") is not None or row.get("warn_upper") is not None:
        errors.append("external failure-only scheme has a synthetic warning")
    return errors


class Tables(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables, self.table, self.row, self.cell = [], None, None, None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.table = []
        elif tag == "tr" and self.table is not None:
            self.row = []
        elif tag in ("th", "td") and self.row is not None:
            self.cell = ""

    def handle_data(self, data):
        if self.cell is not None:
            self.cell += data

    def handle_endtag(self, tag):
        if tag in ("th", "td") and self.cell is not None:
            self.row.append(self.cell.strip())
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.table.append(self.row)
            self.row = None
        elif tag == "table" and self.table is not None:
            self.tables.append(self.table)
            self.table = None


def check_html(text, rows):
    parser = Tables()
    parser.feed(text)
    table = next((t for t in parser.tables if t and t[0] == HEADERS), None)
    if table is None:
        return ["published threshold table is missing"]
    errors, shown = [], {}
    for cells in table[1:]:
        if len(cells) != 5 or cells[0] in shown:
            errors.append("malformed or duplicate threshold table row")
            continue
        try:
            shown[cells[0]] = [number(s) for s in cells[1:]]
        except ValueError:
            errors.append(f"{cells[0]} has an invalid displayed number")
    expected_metrics = {r["metric"] for r in rows}
    # External manifests enumerate unused blank metrics, although their API omits them.
    for row in rows:
        metric = row["metric"]
        if metric not in shown:
            errors.append(f"{metric} is missing from the published table")
            continue
        expected = operational_values(row)
        for key, actual, value in zip(FIELDS, shown[metric], expected):
            if value is not None and abs(value) >= 1000:
                value = float(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
            if not same(actual, value):
                errors.append(f"{metric}/{key}: displayed {actual}, expected {value}")
    for metric in set(shown) - expected_metrics:
        if any(v is not None for v in shown[metric]):
            errors.append(f"unexpected nonblank displayed metric {metric}")
    return errors


def check_native(path, rows, external):
    errors, native = [], {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            metric = ALIASES.get(row.get("metric"), row.get("metric"))
            if metric in native:
                errors.append(f"duplicate native metric {metric}")
            native[metric] = row
    for row in rows:
        metric = row["metric"]
        if metric == "longest":
            continue
        if metric not in native:
            errors.append(f"{metric} missing from native download")
            continue
        cells = native[metric]
        for key, column in [("final_lower", "FINAL_lower"), ("final_upper", "FINAL_upper"),
                            ("warn_lower", "WARN_lower"), ("warn_upper", "WARN_upper")]:
            if key.startswith("warn"):
                fail = "final_lower" if key.endswith("lower") else "final_upper"
                if row.get(fail) is None:
                    continue
            if column not in cells and key.startswith("final"):
                column = "lower_bounds" if key.endswith("lower") else "upper_bounds"
            try:
                actual = number(cells.get(column))
            except ValueError:
                errors.append(f"{metric}/{column}: invalid native number")
                continue
            if metric == "GC_Content" and actual is not None and abs(actual) <= 1.5:
                actual *= 100
            if not same(actual, row.get(key)):
                errors.append(f"{metric}/{key}: native {actual}, API {row.get(key)}")
    return errors


def audit(root, skip_html=False):
    errors, row_count, scheme_count, html_count, native_count = [], 0, 0, 0, 0
    for prefix, external in [("", False), ("external/", True)]:
        base = root / "public" / "api" / "v2" / prefix
        data = json.loads((base / "thresholds.json").read_text())
        index = json.loads((base / "index.json").read_text())
        indexed = {(s["species"], sc["scheme"]) for s in index["species"] for sc in s["schemes"]}
        published = {(sp, sc) for sp, blob in data["species"].items() for sc in blob["schemes"]}
        if indexed != published:
            errors.append(f"{prefix or 'primary'} index/API scheme membership differs")
        for sp, blob in data["species"].items():
            for sc, scheme in blob["schemes"].items():
                scheme_count += 1
                ctx = f"{sp}/{sc}"
                rows = scheme["thresholds"]
                row_count += len(rows)
                metrics = [r.get("metric") for r in rows]
                expected = EXTERNAL if external else PRIMARY | {"longest"}
                if len(metrics) != len(set(metrics)) or set(metrics) != expected:
                    errors.append(f"{ctx}: duplicate, missing or unexpected metric inventory")
                directory = root / "public" / "static" / "species" / sp / sc
                try:
                    manifest = json.loads((directory / "manifest.json").read_text())
                except (OSError, ValueError) as exc:
                    errors.append(f"{ctx}: missing/invalid manifest: {exc}")
                    continue
                manifest_rows = {r["metric"]: r for r in manifest.get("thresholds", [])}
                for row in rows:
                    metric = row.get("metric")
                    errors.extend(f"{ctx}/{metric}: {e}" for e in validate_row(row, external))
                    mr = manifest_rows.get(metric, {})
                    for key in (*FIELDS, "lower", "upper"):
                        if not same(row.get(key), mr.get(key)):
                            errors.append(f"{ctx}/{metric}/{key}: API and manifest differ")
                    if row.get("source") != mr.get("source"):
                        errors.append(f"{ctx}/{metric}: API and manifest source differ")
                native = directory / f"{sp}_metrics.csv"
                if native.exists():
                    native_count += 1
                    errors.extend(f"{ctx}: {e}" for e in check_native(native, rows, external))
                if not skip_html and (root / "out").exists():
                    route = root / "out" / sp.split("_")[0] / sp / sc
                    page = route / "index.html"
                    if not page.exists():
                        page = Path(str(route) + ".html")
                    if not page.exists():
                        errors.append(f"{ctx}: generated page missing")
                    else:
                        html_count += 1
                        errors.extend(f"{ctx}: {e}" for e in check_html(page.read_text(), rows))
    return errors, {"schemes": scheme_count, "API_rows": row_count,
                    "native_downloads": native_count, "generated_pages": html_count}


def self_test():
    row = dict(metric="GC_Content", lower=38.68, upper=39.75,
               final_lower=38.68, warn_lower=38.8, warn_upper=39.17, final_upper=39.75)
    assert not validate_row(row)
    reversed_row = {**row, "upper": 37, "final_upper": 37}
    assert any("exceeds" in e for e in validate_row(reversed_row))
    missing_warning = {**row, "warn_lower": None}
    assert any("missing operational" in e for e in validate_row(missing_warning))
    outside_warning = {**row, "warn_upper": 40}
    assert any("outside failure" in e for e in validate_row(outside_warning))
    header = "<table><tr>" + "".join(f"<th>{s}</th>" for s in HEADERS) + "</tr>"
    exact = header + "<tr><td>GC_Content</td><td>38.68</td><td>38.8</td><td>39.17</td><td>39.75</td></tr></table>"
    assert not check_html(exact, [row])
    widened = exact.replace("38.68", "38.6").replace("39.75", "39.8")
    assert len(check_html(widened, [row])) == 2
    one_sided = dict(metric="N50", lower=20000, upper=None, final_lower=20000,
                     final_upper=None, warn_lower=23000, warn_upper=400000)
    assert not validate_row(one_sided)
    external = copy.deepcopy(one_sided)
    external.update(warn_lower=None, warn_upper=None)
    assert not validate_row(external, external=True)
    with tempfile.TemporaryDirectory() as temporary:
        native = Path(temporary) / "metrics.csv"
        native.write_text("metric,FINAL_lower,FINAL_upper,WARN_lower,WARN_upper\n"
                          "GC_Content,38.68,39.75,38.8,39.17\n")
        assert not check_native(native, [row], external=False)
        native.write_text("metric,FINAL_lower,FINAL_upper,WARN_lower,WARN_upper\n"
                          "GC_Content,38.68,39.75,,\n")
        missing_native = check_native(native, [row], external=False)
        assert len(missing_native) == 2 and all("native None" in e for e in missing_native)
    print("PASS: valid, reversed, missing-warning, outside-warning, GC display, native CSV and one-sided cases")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--skip-html", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    errors, counts = audit(args.root, args.skip_html)
    print(json.dumps(counts, sort_keys=True))
    for error in errors[:60]:
        print("FAIL:", error)
    if len(errors) > 60:
        print(f"... {len(errors) - 60} additional errors")
    print(f"{'FAIL' if errors else 'PASS'}: {len(errors)} consistency error(s)")
    return bool(errors)


if __name__ == "__main__":
    raise SystemExit(main())
