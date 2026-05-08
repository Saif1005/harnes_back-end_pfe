from __future__ import annotations

import csv
import sqlite3
import zipfile
import xml.etree.ElementTree as ET
from functools import lru_cache
from pathlib import Path
from typing import Any

from harness_backend.config.settings import SETTINGS
from harness_backend.services.legacy_compat import find_inventory_match, normalize_key
from harness_backend.tools.implementations.classification_tools import run_material_classification


def _safe_path(configured_path: str, fallback_path: str) -> Path:
    path = Path(configured_path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
    except OSError:
        fb = Path(fallback_path)
        fb.parent.mkdir(parents=True, exist_ok=True)
        return fb


def _connect() -> sqlite3.Connection:
    db_path = _safe_path(SETTINGS.stock_runtime_path, "/tmp/harness/stock_runtime.sqlite")
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def init_stock_runtime_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS stock_items (
                material_key TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                label TEXT NOT NULL,
                quantity_kg REAL NOT NULL DEFAULT 0,
                unit TEXT NOT NULL DEFAULT 'kg',
                material_code TEXT NOT NULL DEFAULT '',
                source_date TEXT NOT NULL DEFAULT ''
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS stock_movements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                movement_type TEXT NOT NULL,
                material_key TEXT NOT NULL,
                delta_kg REAL NOT NULL,
                run_id TEXT NOT NULL DEFAULT '',
                reason TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS stock_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                stock_date TEXT NOT NULL,
                material_code TEXT NOT NULL,
                display_name TEXT NOT NULL,
                label TEXT NOT NULL,
                sub_family TEXT NOT NULL DEFAULT '',
                quantity REAL NOT NULL DEFAULT 0,
                unit TEXT NOT NULL DEFAULT '',
                quantity_kg REAL NOT NULL DEFAULT 0
            )
            """
        )
        # Backward-compatible migrations for already-created DBs.
        existing_cols = {
            str(r["name"])
            for r in conn.execute("PRAGMA table_info(stock_items)").fetchall()
        }
        if "unit" not in existing_cols:
            conn.execute("ALTER TABLE stock_items ADD COLUMN unit TEXT NOT NULL DEFAULT 'kg'")
        if "material_code" not in existing_cols:
            conn.execute("ALTER TABLE stock_items ADD COLUMN material_code TEXT NOT NULL DEFAULT ''")
        if "source_date" not in existing_cols:
            conn.execute("ALTER TABLE stock_items ADD COLUMN source_date TEXT NOT NULL DEFAULT ''")
        conn.commit()


def map_legacy_dataset(
    source_path: str | None = None,
    target_path: str | None = None,
    classify_missing_labels: bool = True,
    classify_all: bool = False,
    production_only: bool = True,
    article_reference_path: str | None = None,
) -> dict[str, Any]:
    src = source_path or SETTINGS.dataset_classification_path
    out = target_path or SETTINGS.stock_mapped_dataset_path
    out_path = _safe_path(out, "/tmp/harness/dataset_stock_mapped.csv")
    rows = 0
    classified_rows = 0
    lookup = _load_article_lookup(article_reference_path)
    ingredient_keys = _load_recipe_ingredient_keys()
    with open(out_path, "w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=["texte", "label", "quantity_kg"])
        writer.writeheader()
        for raw in _iter_source_rows(src):
            if production_only and not _is_production_consumption(raw):
                continue
            text = str(
                raw.get("texte")
                or raw.get("designation")
                or raw.get("designation_article")
                or raw.get("description")
                or raw.get("Description_1")
                or raw.get("Description_2")
                or raw.get("libelle")
                or ""
            ).strip()
            if not text:
                continue
            label = str(raw.get("label") or raw.get("categorie") or raw.get("type") or "").strip().upper()
            if not label:
                label = _lookup_label_from_erp(raw, lookup)
            qty_raw = (
                raw.get("quantity_kg")
                or raw.get("quantite")
                or raw.get("qte")
                or raw.get("stock")
                or raw.get("Quantity")
                or 0
            )
            try:
                qty = abs(float(str(qty_raw).replace(",", ".").strip() or 0.0))
            except ValueError:
                qty = 0.0
            if classify_all or (classify_missing_labels and not label):
                pred = run_material_classification(text)
                pred_label = str((pred or {}).get("label", "")).upper().strip()
                if pred_label in {"MP", "PDR", "CHIMIE"}:
                    label = pred_label
                    classified_rows += 1

            label = _apply_contextual_label_policy(text=text, current_label=label, ingredient_keys=ingredient_keys)
            if not label:
                low = text.lower()
                if any(k in low for k in ("acide", "soude", "amidon", "asa", "ppo", "pac", "biocide")):
                    label = "CHIMIE"
                elif any(k in low for k in ("roulement", "courroie", "vis", "joint", "moteur", "pompe")):
                    label = "PDR"
                else:
                    label = "MP"
            writer.writerow({"texte": text, "label": label, "quantity_kg": round(qty, 3)})
            rows += 1
    return {
        "rows": rows,
        "classified_rows": classified_rows,
        "target_path": str(out_path),
        "source_path": src,
        "classification_mode": "all_rows" if classify_all else "missing_labels_only",
        "production_only": production_only,
        "article_lookup_size": len(lookup),
    }


def _iter_source_rows(path: str) -> Any:
    if path.lower().endswith(".xlsx"):
        yield from _iter_xlsx_rows(path)
        return
    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            yield row


def _iter_xlsx_rows(path: str) -> Any:
    ns = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main", "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
    with zipfile.ZipFile(path) as zf:
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in zf.namelist():
            root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in root.findall("a:si", ns):
                tokens = [t.text or "" for t in si.findall(".//a:t", ns)]
                shared_strings.append("".join(tokens))

        rels_xml = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        rid_to_target = {rel.attrib.get("Id", ""): rel.attrib.get("Target", "") for rel in rels_xml}
        workbook_xml = ET.fromstring(zf.read("xl/workbook.xml"))
        first_sheet = workbook_xml.find("a:sheets/a:sheet", ns)
        if first_sheet is None:
            return
        rid = first_sheet.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id", "")
        target = rid_to_target.get(rid, "worksheets/sheet1.xml")
        sheet_path = target if target.startswith("xl/") else f"xl/{target}"
        sheet_xml = ET.fromstring(zf.read(sheet_path))

        def _cell_value(cell: ET.Element) -> str:
            tpe = cell.attrib.get("t")
            v = cell.find("a:v", ns)
            if v is None:
                return ""
            raw = v.text or ""
            if tpe == "s":
                try:
                    return shared_strings[int(raw)]
                except Exception:  # noqa: BLE001
                    return raw
            return raw

        def _col_ref(cell_ref: str) -> str:
            return "".join(ch for ch in cell_ref if ch.isalpha())

        header_map: dict[str, str] = {}
        for row in sheet_xml.findall(".//a:sheetData/a:row", ns):
            rec: dict[str, str] = {}
            for cell in row.findall("a:c", ns):
                col = _col_ref(cell.attrib.get("r", ""))
                rec[col] = _cell_value(cell)
            if not header_map:
                header_map = {k: str(v).strip() for k, v in rec.items()}
                continue
            out: dict[str, str] = {}
            for col, val in rec.items():
                key = header_map.get(col, col)
                out[key] = val
            yield out


def _is_production_consumption(row: dict[str, Any]) -> bool:
    reason = str(row.get("Reason Code") or row.get("reason_code") or "").strip().upper()
    document_no = str(row.get("Document No_") or row.get("document_no") or "").strip().upper()
    entry_type = str(row.get("Entry Type") or row.get("entry_type") or "").strip()
    document_type = str(row.get("Document Type") or row.get("document_type") or "").strip()
    location = str(row.get("Location Code") or row.get("location") or "").strip().upper()
    quantity_raw = str(row.get("Quantity") or row.get("quantity_kg") or row.get("qte") or "0").replace(",", ".").strip()
    try:
        quantity = float(quantity_raw or 0.0)
    except ValueError:
        quantity = 0.0

    text_blob = " ".join(
        [
            str(row.get("Description_1") or row.get("description") or ""),
            str(row.get("Description_2") or ""),
            str(row.get("Code machine") or ""),
        ]
    ).upper()

    if reason == "CONSO":
        return True
    if quantity < 0 and document_type in {"25", "5"}:
        return True
    if document_no.startswith("CONS") or document_no.startswith("PROD"):
        return True
    if "PULPEUR" in text_blob or "MACHINE" in text_blob:
        return True
    if location in {"PRINCIPAL", "SECONDAIRE"} and entry_type in {"3", "4"} and quantity < 0:
        return True
    return False


def _to_kg(quantity: float, unit: str) -> float:
    u = (unit or "").strip().lower()
    if u in {"tonne", "tonnes", "t"}:
        return float(quantity) * 1000.0
    if u in {"kg", "kilogramme", "kilogrammes"}:
        return float(quantity)
    # For piece-based inventories (PDR), keep numeric value as-is for runtime reasoning.
    return float(quantity)


def import_official_stock_history(source_path: str | None = None) -> dict[str, Any]:
    """
    Import official stock history CSV into SQLite and rebuild current stock_items
    from latest snapshot date per ERP code.
    """
    src = source_path or SETTINGS.stock_official_history_path
    p = Path(src)
    if not p.exists():
        raise FileNotFoundError(f"official_stock_history_not_found: {src}")

    init_stock_runtime_db()
    rows = 0
    latest_by_code: dict[str, dict[str, Any]] = {}
    label_counts = {"MP": 0, "CHIMIE": 0, "PDR": 0}

    with _connect() as conn:
        conn.execute("DELETE FROM stock_history")
        with p.open("r", encoding="utf-8", errors="ignore") as fh:
            reader = csv.DictReader(fh)
            for raw in reader:
                code = str(raw.get("Code_ERP", "")).strip()
                name = str(raw.get("Désignation") or raw.get("Designation") or "").strip()
                fam = str(raw.get("Famille", "")).strip().upper()
                sub_family = str(raw.get("Sous_Famille", "")).strip()
                stock_date = str(raw.get("Date", "")).strip()
                unit = str(raw.get("Unité_Stock") or raw.get("Unite_Stock") or raw.get("Unité") or "").strip()
                qty_raw = str(raw.get("Quantité_Stock") or raw.get("Quantite_Stock") or "0").replace(",", ".").strip()
                try:
                    qty = float(qty_raw or 0.0)
                except ValueError:
                    qty = 0.0
                label = "CHIMIE" if fam in {"CHIME", "CHIMIE"} else ("PDR" if fam == "PDR" else "MP")
                qty_kg = _to_kg(qty, unit)
                rows += 1
                conn.execute(
                    """
                    INSERT INTO stock_history(stock_date, material_code, display_name, label, sub_family, quantity, unit, quantity_kg)
                    VALUES(?,?,?,?,?,?,?,?)
                    """,
                    (stock_date, code, name, label, sub_family, qty, unit, qty_kg),
                )
                prev = latest_by_code.get(code)
                if prev is None or stock_date >= str(prev.get("stock_date", "")):
                    latest_by_code[code] = {
                        "stock_date": stock_date,
                        "display_name": name or code,
                        "label": label,
                        "quantity_kg": max(0.0, qty_kg),
                        "unit": unit or "kg",
                        "material_code": code,
                    }

        conn.execute("DELETE FROM stock_items")
        for code, val in latest_by_code.items():
            display = str(val.get("display_name", code))
            key = normalize_key(code) or normalize_key(display) or code.lower()
            label = str(val.get("label", "MP")).upper()
            if label in label_counts:
                label_counts[label] += 1
            conn.execute(
                """
                INSERT INTO stock_items(material_key, display_name, label, quantity_kg, unit, material_code, source_date)
                VALUES(?,?,?,?,?,?,?)
                """,
                (
                    key,
                    display,
                    label,
                    float(val.get("quantity_kg", 0.0) or 0.0),
                    str(val.get("unit", "kg")),
                    str(val.get("material_code", code)),
                    str(val.get("stock_date", "")),
                ),
            )
        conn.commit()

    return {
        "source_path": src,
        "history_rows": rows,
        "current_items": len(latest_by_code),
        "label_item_counts": label_counts,
    }


@lru_cache(maxsize=4)
def _load_recipe_ingredient_keys() -> set[str]:
    keys: set[str] = set()
    path = Path(SETTINGS.recipe_correlation_path)
    if not path.exists():
        return keys
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                ingredient = str(row.get("ingredient", "")).strip()
                if ingredient:
                    keys.add(normalize_key(ingredient))
    except Exception:
        return keys
    return keys


def _load_article_lookup(path: str | None) -> dict[str, str]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    out: dict[str, str] = {}
    try:
        with p.open("r", encoding="utf-8", errors="ignore") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                item = str(row.get("No_") or row.get("Item No_") or "").strip()
                posting = str(row.get("Inventory Posting Group") or row.get("Type") or "").strip().upper()
                if not item:
                    continue
                label = ""
                if "CHIM" in posting:
                    label = "CHIMIE"
                elif "PDR" in posting or "MACHINE" in posting:
                    label = "PDR"
                elif "MP" in posting or "MAT" in posting:
                    label = "MP"
                if label:
                    out[item] = label
    except Exception:
        return {}
    return out


def _lookup_label_from_erp(row: dict[str, Any], lookup: dict[str, str]) -> str:
    if not lookup:
        return ""
    item_no = str(row.get("Item No_") or row.get("No_") or row.get("item_no") or "").strip()
    if not item_no:
        return ""
    return str(lookup.get(item_no, "")).upper().strip()


def _apply_contextual_label_policy(text: str, current_label: str, ingredient_keys: set[str]) -> str:
    label = str(current_label or "").upper().strip()
    low = (text or "").lower()
    key = normalize_key(text)

    # Explicit machine/fuel consumables must be PDR.
    if any(
        tok in low
        for tok in (
            "gazoil",
            "gazole",
            "diesel",
            "huile hydraulique",
            "huile moteur",
            "lubrifiant",
            "graisse",
            "carburant",
            "filtre",
            "roulement",
            "courroie",
            "joint",
            "pignon",
            "pompe",
            "moteur",
            "pulpeur",
        )
    ):
        return "PDR"

    # Ingredients present in recipe correlation are production consumables.
    if key and key in ingredient_keys:
        if any(k in low for k in ("acide", "soude", "amidon", "asa", "ppo", "pac", "biocide")):
            return "CHIMIE"
        return "MP"

    return label


def rebuild_stock_base_from_dataset(dataset_path: str | None = None) -> dict[str, Any]:
    source = dataset_path or SETTINGS.stock_mapped_dataset_path
    if not Path(source).exists():
        source = SETTINGS.dataset_classification_path
    agg: dict[str, dict[str, Any]] = {}
    with open(source, "r", encoding="utf-8", errors="ignore") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            text = str(row.get("texte", "")).strip()
            if not text:
                continue
            key = normalize_key(text)
            if not key:
                continue
            qty = abs(float(row.get("quantity_kg", 0.0) or 0.0))
            label = str(row.get("label", "MP")).strip().upper() or "MP"
            data = agg.setdefault(key, {"display_name": text, "label": label, "quantity_kg": 0.0})
            data["quantity_kg"] = float(data["quantity_kg"]) + qty
    init_stock_runtime_db()
    with _connect() as conn:
        conn.execute("DELETE FROM stock_items")
        for key, val in agg.items():
            conn.execute(
                "INSERT INTO stock_items(material_key, display_name, label, quantity_kg) VALUES(?,?,?,?)",
                (key, str(val["display_name"]), str(val["label"]), float(val["quantity_kg"])),
            )
        conn.commit()
    return {"items": len(agg), "dataset_path": source}


def get_inventory_state() -> dict[str, Any]:
    init_stock_runtime_db()
    totals = {"MP": 0.0, "CHIMIE": 0.0, "PDR": 0.0}
    inventory_map: dict[str, float] = {}
    inventory_labels: dict[str, str] = {}
    inventory_displays: dict[str, str] = {}
    with _connect() as conn:
        rows = conn.execute(
            "SELECT material_key, label, quantity_kg, display_name FROM stock_items"
        ).fetchall()
        for r in rows:
            key = str(r["material_key"])
            label = str(r["label"]).upper()
            qty = float(r["quantity_kg"] or 0.0)
            inventory_map[key] = qty
            inventory_labels[key] = label
            inventory_displays[key] = str(r["display_name"] or "")
            if label in totals:
                totals[label] += qty
    return {
        "totals_kg": {k: round(v, 3) for k, v in totals.items()},
        "inventory_map": {k: round(v, 3) for k, v in inventory_map.items()},
        "inventory_labels": inventory_labels,
        "inventory_displays": inventory_displays,
        "source": "stock_runtime_sqlite",
    }


def apply_recipe_consumption(recipe_items: list[dict[str, Any]], run_id: str, reason: str) -> dict[str, Any]:
    state = get_inventory_state()
    inventory = dict(state.get("inventory_map") or {})
    displays = dict(state.get("inventory_displays") or {})
    labels = dict(state.get("inventory_labels") or {})
    updates: list[dict[str, Any]] = []
    init_stock_runtime_db()
    with _connect() as conn:
        for item in recipe_items:
            ingredient = str(item.get("ingredient", "")).strip()
            required_kg = float(item.get("required_kg", 0.0) or 0.0)
            if not ingredient or required_kg <= 0:
                continue
            matched_key, available_kg = find_inventory_match(ingredient, inventory, displays, labels)
            if not matched_key:
                continue
            consumed = min(required_kg, available_kg)
            conn.execute(
                "UPDATE stock_items SET quantity_kg = MAX(quantity_kg - ?, 0) WHERE material_key = ?",
                (consumed, matched_key),
            )
            conn.execute(
                """
                INSERT INTO stock_movements(movement_type, material_key, delta_kg, run_id, reason)
                VALUES(?,?,?,?,?)
                """,
                ("consume", matched_key, -consumed, run_id, reason),
            )
            inventory[matched_key] = max(0.0, available_kg - consumed)
            updates.append(
                {
                    "ingredient": ingredient,
                    "material_key": matched_key,
                    "consumed_kg": round(consumed, 3),
                    "required_kg": round(required_kg, 3),
                }
            )
        conn.commit()
    return {"updates": updates, "count": len(updates)}


def get_prediction_series(limit: int = 500) -> dict[str, list[float]]:
    init_stock_runtime_db()
    series: dict[str, list[float]] = {"MP": [], "CHIMIE": [], "PDR": []}
    with _connect() as conn:
        rows = conn.execute("SELECT label, quantity_kg FROM stock_items").fetchall()
        for r in rows:
            label = str(r["label"]).upper()
            if label in series:
                series[label].append(float(r["quantity_kg"] or 0.0))
        mov = conn.execute(
            """
            SELECT s.label AS label, ABS(m.delta_kg) AS val
            FROM stock_movements m
            JOIN stock_items s ON s.material_key = m.material_key
            ORDER BY m.id DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
        for r in mov:
            label = str(r["label"]).upper()
            if label in series:
                series[label].append(float(r["val"] or 0.0))
    return series


def apply_stock_adjustments(
    adjustments: list[dict[str, Any]],
    run_id: str,
    reason: str,
) -> dict[str, Any]:
    """
    Dynamic stock updates (+/-) with movement journaling.
    Supports matching by material_key, material_code, or display_name.
    """
    init_stock_runtime_db()
    updates: list[dict[str, Any]] = []
    with _connect() as conn:
        for adj in adjustments:
            key_in = str(adj.get("material_key", "")).strip()
            code_in = str(adj.get("material_code", "")).strip()
            name_in = str(adj.get("display_name", "")).strip()
            delta = float(adj.get("delta_kg", 0.0) or 0.0)
            if delta == 0:
                continue

            row = None
            if key_in:
                row = conn.execute(
                    "SELECT material_key, quantity_kg FROM stock_items WHERE material_key = ?",
                    (normalize_key(key_in),),
                ).fetchone()
            if row is None and code_in:
                row = conn.execute(
                    "SELECT material_key, quantity_kg FROM stock_items WHERE material_code = ?",
                    (code_in,),
                ).fetchone()
            if row is None and name_in:
                row = conn.execute(
                    "SELECT material_key, quantity_kg FROM stock_items WHERE material_key = ?",
                    (normalize_key(name_in),),
                ).fetchone()
            if row is None:
                continue

            material_key = str(row["material_key"])
            current = float(row["quantity_kg"] or 0.0)
            new_val = max(0.0, current + delta)
            applied = new_val - current
            if applied == 0:
                continue

            conn.execute(
                "UPDATE stock_items SET quantity_kg = ? WHERE material_key = ?",
                (new_val, material_key),
            )
            conn.execute(
                """
                INSERT INTO stock_movements(movement_type, material_key, delta_kg, run_id, reason)
                VALUES(?,?,?,?,?)
                """,
                ("adjust", material_key, applied, run_id, reason),
            )
            updates.append(
                {
                    "material_key": material_key,
                    "before_kg": round(current, 3),
                    "after_kg": round(new_val, 3),
                    "applied_delta_kg": round(applied, 3),
                }
            )
        conn.commit()
    return {"count": len(updates), "updates": updates}


def build_restock_plan(
    label: str | None = None,
    min_quantity_kg: float = 10.0,
    target_quantity_kg: float = 100.0,
    limit: int = 200,
) -> dict[str, Any]:
    """
    Propose restock actions for low-stock items.
    - label: optional filter (MP/CHIMIE/PDR)
    - min_quantity_kg: below this threshold -> candidate
    - target_quantity_kg: suggested post-restock target
    """
    init_stock_runtime_db()
    norm_label = str(label or "").upper().strip()
    candidates: list[dict[str, Any]] = []
    with _connect() as conn:
        if norm_label in {"MP", "CHIMIE", "PDR"}:
            rows = conn.execute(
                """
                SELECT material_key, material_code, display_name, label, quantity_kg
                FROM stock_items
                WHERE label = ? AND quantity_kg <= ?
                ORDER BY quantity_kg ASC
                LIMIT ?
                """,
                (norm_label, float(min_quantity_kg), int(limit)),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT material_key, material_code, display_name, label, quantity_kg
                FROM stock_items
                WHERE quantity_kg <= ?
                ORDER BY quantity_kg ASC
                LIMIT ?
                """,
                (float(min_quantity_kg), int(limit)),
            ).fetchall()

    for r in rows:
        qty = float(r["quantity_kg"] or 0.0)
        delta = max(0.0, float(target_quantity_kg) - qty)
        if delta <= 0:
            continue
        candidates.append(
            {
                "material_key": str(r["material_key"]),
                "material_code": str(r["material_code"] or ""),
                "display_name": str(r["display_name"] or ""),
                "label": str(r["label"] or ""),
                "current_kg": round(qty, 3),
                "target_kg": round(float(target_quantity_kg), 3),
                "proposed_delta_kg": round(delta, 3),
            }
        )
    return {
        "count": len(candidates),
        "min_quantity_kg": float(min_quantity_kg),
        "target_quantity_kg": float(target_quantity_kg),
        "items": candidates,
    }

