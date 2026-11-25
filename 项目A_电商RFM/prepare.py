# -*- coding: utf-8 -*-
"""
项目 A · 电商用户行为分析：数据准备
- 自动下载 Online Retail 真实交易数据（公开数据集，无需注册）
- 清洗后写入 SQLite：data/retail.db（表 transactions）
运行：python prepare.py
"""
import os
import urllib.request

import pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
os.makedirs(DATA, exist_ok=True)

# 主源：GitHub 镜像（国内可达，实测 200/43.9MB）；备源：raw 直连
SOURCES = [
    "https://ghfast.top/https://raw.githubusercontent.com/guipsamora/pandas_exercises/master/07_Visualization/Online_Retail/Online_Retail.csv",
    "https://raw.githubusercontent.com/guipsamora/pandas_exercises/master/07_Visualization/Online_Retail/Online_Retail.csv",
]
CSV = os.path.join(DATA, "online_retail.csv")


def download():
    if os.path.exists(CSV) and os.path.getsize(CSV) > 5_000_000:
        print(f"[skip] 已存在 {os.path.basename(CSV)} {os.path.getsize(CSV)/1e6:.1f} MB")
        return CSV
    for url in SOURCES:
        print(f"[download] {url}")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=180) as r, open(CSV, "wb") as f:
                f.write(r.read())
            if os.path.getsize(CSV) > 5_000_000:
                print(f"[ok] {os.path.getsize(CSV)/1e6:.1f} MB")
                return CSV
            print("[warn] 文件过小，换备源")
        except Exception as e:
            print(f"[fail] {e}")
    raise SystemExit("下载失败：检查网络或换源")


def load_csv(path):
    for enc in ("utf-8", "latin1"):
        try:
            df = pd.read_csv(path, encoding=enc)
            print(f"[read] encoding={enc} rows={len(df)} cols={list(df.columns)}")
            return df
        except UnicodeDecodeError:
            continue
    raise SystemExit("CSV 编码无法识别")


def clean(df):
    df.columns = [str(c).strip() for c in df.columns]
    rename = {
        "InvoiceNo": "invoice_no", "Invoice": "invoice_no",
        "StockCode": "stock_code", "Description": "description",
        "Quantity": "quantity", "InvoiceDate": "invoice_date",
        "UnitPrice": "unit_price", "Price": "unit_price",
        "Customer ID": "customer_id", "CustomerID": "customer_id",
        "Country": "country",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
    need = ["invoice_no", "stock_code", "quantity", "invoice_date", "unit_price", "customer_id"]
    missing = [c for c in need if c not in df.columns]
    if missing:
        raise SystemExit(f"字段缺失: {missing}  实际字段: {list(df.columns)}")

    n0 = len(df)
    df["invoice_date"] = pd.to_datetime(df["invoice_date"], errors="coerce", format="mixed")
    df["customer_id"] = pd.to_numeric(df["customer_id"], errors="coerce")
    df = df.dropna(subset=["customer_id", "invoice_date", "quantity", "unit_price"])
    df["customer_id"] = df["customer_id"].astype("int64")
    df = df[df["invoice_no"].astype(str).str.match(r"^\d{6}")]       # 只留正常订单（剔除 C 取消单）
    df = df[(df["quantity"] > 0) & (df["unit_price"] > 0)]           # 剔除退货/异常
    df["amount"] = (df["quantity"] * df["unit_price"]).round(2)
    df = df[["invoice_no", "stock_code", "description", "quantity", "invoice_date",
             "unit_price", "customer_id", "country", "amount"]]
    print(f"[clean] {n0} -> {len(df)} 行（去取消单/退货/空客户）")
    return df


def to_sqlite(df):
    import sqlite3
    db = os.path.join(DATA, "retail.db")
    if os.path.exists(db):
        os.remove(db)
    conn = sqlite3.connect(db)
    df.to_sql("transactions", conn, index=False)
    conn.execute("CREATE INDEX idx_cust ON transactions(customer_id)")
    conn.execute("CREATE INDEX idx_date ON transactions(invoice_date)")
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    c = conn.execute("SELECT COUNT(DISTINCT customer_id) FROM transactions").fetchone()[0]
    lo, hi = conn.execute("SELECT MIN(invoice_date), MAX(invoice_date) FROM transactions").fetchone()
    gmv = conn.execute("SELECT ROUND(SUM(amount),2) FROM transactions").fetchone()[0]
    print(f"[db] {db}")
    print(f"[stats] 行数={n}  客户数={c}  时间={lo} ~ {hi}  总金额={gmv}")
    conn.close()


if __name__ == "__main__":
    path = download()
    raw = load_csv(path)
    tidy = clean(raw)
    to_sqlite(tidy)
    print("[done] 下一步：python analysis.py")
