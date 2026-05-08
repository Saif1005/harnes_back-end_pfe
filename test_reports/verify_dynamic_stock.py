import json, urllib.request, sqlite3
BASE="http://127.0.0.1:8030"
DB="/opt/harness/db/stock_runtime.sqlite"

def post(path,payload):
    req=urllib.request.Request(BASE+path,data=json.dumps(payload).encode(),headers={"Content-Type":"application/json"},method="POST")
    with urllib.request.urlopen(req,timeout=180) as r:
        return json.loads(r.read().decode())

post("/admin/data/import-official-stock",{"source_path":"/opt/harness/data/magasin_stock_historique_2017_2023.csv"})

con=sqlite3.connect(DB); cur=con.cursor()
item=cur.execute("select material_key, quantity_kg from stock_items where label='PDR' and quantity_kg > 10 limit 1").fetchone()
if item is None:
    raise RuntimeError("no_pdr_item_found")
mk=item[0]; before=float(item[1])
mov_before=cur.execute("select count(*) from stock_movements").fetchone()[0]
con.close()

post("/admin/data/adjust-stock",{"run_id":"verify-adjust","reason":"restock test","adjustments":[{"material_key":mk,"delta_kg":50.0}]})
post("/admin/data/adjust-stock",{"run_id":"verify-adjust","reason":"consume test","adjustments":[{"material_key":mk,"delta_kg":-20.0}]})

con=sqlite3.connect(DB); cur=con.cursor()
after=float(cur.execute("select quantity_kg from stock_items where material_key=?",(mk,)).fetchone()[0])
mov_after=cur.execute("select count(*) from stock_movements").fetchone()[0]
last=cur.execute("select movement_type, material_key, delta_kg, reason from stock_movements order by id desc limit 3").fetchall()
con.close()

stock=post("/tools/stock",{"query":"verif stock dynamique"})
out={
  "material_key":mk,
  "qty_before":before,
  "qty_after":after,
  "applied_delta_expected":30.0,
  "applied_delta_real":round(after-before,3),
  "movements_added":mov_after-mov_before,
  "stock_tool_source":stock.get("source"),
  "last_movements":last
}
print(json.dumps(out,ensure_ascii=True))
