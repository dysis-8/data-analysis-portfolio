# -*- coding: utf-8 -*-
"""
项目 A · 电商用户行为分析：SQL 分析 + 报告数据
- 复购率、月度 GMV、RFM 分层、留存
- 结果写入 reports/result.md 和 reports/result.json
运行：python analysis.py
"""
import os
import json
import sqlite3
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "data", "retail.db")
OUT = os.path.join(BASE, "reports")
os.makedirs(OUT, exist_ok=True)

QUERIES = {
    "总览": """
        SELECT COUNT(*) AS 行数,
               COUNT(DISTINCT customer_id) AS 客户数,
               COUNT(DISTINCT invoice_no) AS 订单数,
               ROUND(SUM(amount), 2) AS 总金额
        FROM transactions
    """,
    "复购率": """
        WITH per_cust AS (
            SELECT customer_id, COUNT(DISTINCT invoice_no) AS orders
            FROM transactions GROUP BY customer_id
        )
        SELECT ROUND(1.0 * SUM(CASE WHEN orders >= 2 THEN 1 ELSE 0 END) / COUNT(*), 4) AS 复购率,
               COUNT(*) AS 客户数,
               ROUND(AVG(orders), 2) AS 人均订单数
        FROM per_cust
    """,
    "月度GMV": """
        SELECT strftime('%Y-%m', invoice_date) AS 月份,
               ROUND(SUM(amount), 2) AS GMV,
               COUNT(DISTINCT invoice_no) AS 订单数
        FROM transactions
        GROUP BY 1 ORDER BY 1
    """,
    "RFM": """
        WITH last_day AS (SELECT MAX(date(invoice_date)) AS d FROM transactions),
        agg AS (
            SELECT customer_id,
                   MAX(date(invoice_date)) AS last_buy,
                   COUNT(DISTINCT invoice_no) AS frequency,
                   ROUND(SUM(amount), 2) AS monetary
            FROM transactions GROUP BY customer_id
        )
        SELECT customer_id, frequency, monetary,
               CAST(julianday((SELECT d FROM last_day)) - julianday(last_buy) AS INTEGER) AS recency
        FROM agg
    """,
    "留存": """
        WITH first_buy AS (
            SELECT customer_id, MIN(date(invoice_date)) AS first_day
            FROM transactions GROUP BY customer_id
        ),
        later AS (
            SELECT t.customer_id,
                   julianday(date(t.invoice_date)) - julianday(f.first_day) AS gap
            FROM transactions t JOIN first_buy f USING (customer_id)
        )
        SELECT CASE
                 WHEN gap <= 30 THEN '0-30天'
                 WHEN gap <= 60 THEN '31-60天'
                 WHEN gap <= 90 THEN '61-90天'
                 ELSE '90天以上'
               END AS 窗口,
               COUNT(DISTINCT customer_id) AS 复购客户数
        FROM later WHERE gap > 0 GROUP BY 1 ORDER BY 1
    """,
}


def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    out = {}
    lines = ["# 项目 A · 电商用户行为分析结果", "",
             f"> 生成时间：{datetime.now():%Y-%m-%d %H:%M}｜数据：UCI Online Retail II（已清洗）", ""]

    for name, sql in QUERIES.items():
        rows = [dict(r) for r in conn.execute(sql).fetchall()]
        out[name] = rows
        lines.append(f"## {name}")
        lines.append("")
        if not rows:
            lines.append("（空）")
            lines.append("")
            continue
        cols = list(rows[0].keys())
        lines.append("| " + " | ".join(cols) + " |")
        lines.append("|" + "---|" * len(cols))
        for r in rows[:24]:
            lines.append("| " + " | ".join(str(r[c]) for c in cols) + " |")
        lines.append("")

    # RFM 打标签（在 Python 里做，SQL 只取数）
    rfm = out.get("RFM", [])
    if rfm:
        import statistics as st
        med = {k: st.median([r[k] for r in rfm]) for k in ("recency", "frequency", "monetary")}
        seg, seg_money = {}, {}
        for r in rfm:
            key = (("R高" if r["recency"] <= med["recency"] else "R低") +
                   ("F高" if r["frequency"] >= med["frequency"] else "F低") +
                   ("M高" if r["monetary"] >= med["monetary"] else "M低"))
            seg[key] = seg.get(key, 0) + 1
            seg_money[key] = seg_money.get(key, 0) + r["monetary"]
        total_money = sum(seg_money.values()) or 1
        out["RFM分层"] = [{"分层": k, "客户数": v, "客户占比": round(v / len(rfm), 4),
                          "销售额占比": round(seg_money[k] / total_money, 4)}
                         for k, v in sorted(seg.items(), key=lambda x: -seg_money[x[0]])]
        lines.append("## RFM 分层（按中位数切分；R高＝最近有购买）")
        lines.append("")
        lines.append("| 分层 | 客户数 | 客户占比 | 销售额占比 |")
        lines.append("|---|---|---|---|")
        for r in out["RFM分层"]:
            lines.append(f"| {r['分层']} | {r['客户数']} | {r['客户占比']} | {r['销售额占比']} |")
        lines.append("")

        # 关键结论：核心客户 / 高价值流失预警
        core = [r for r in out["RFM分层"] if r["分层"] == "R高F高M高"]
        risk = [r for r in out["RFM分层"] if r["分层"] == "R低F高M高"]
        if core:
            out["核心客户"] = core[0]
            lines.append(f"**核心客户（R高F高M高）**：{core[0]['客户数']} 人（{core[0]['客户占比']:.1%}），"
                         f"贡献 {core[0]['销售额占比']:.1%} 销售额。")
        if risk:
            out["高价值流失预警"] = risk[0]
            lines.append(f"**高价值但久未购买（R低F高M高）**：{risk[0]['客户数']} 人，"
                         f"占销售额 {risk[0]['销售额占比']:.1%}——最该做召回的群体。")
        lines.append("")

    with open(os.path.join(OUT, "result.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    with open(os.path.join(OUT, "result.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    conn.close()
    print("[done] reports/result.md")
    print("\n".join(lines[:40]))


if __name__ == "__main__":
    main()
