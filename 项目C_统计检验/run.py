# -*- coding: utf-8 -*-
"""
项目 C · 统计推断小专题：客户分层的差异到底显著吗？
- 业务问题：核心客户（R高F高M高）与非核心客户的客单价差异，是真实差异还是随机波动？
- 方法：两独立样本置换检验（Permutation test）+ Bootstrap 置信区间 + Cohen's d
- 数据：项目 A 的 data/retail.db，不新增数据
运行：python run.py
"""
import os
import json
import sqlite3

import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.abspath(os.path.join(BASE, "..", "项目A_电商RFM", "data", "retail.db"))
OUT = os.path.join(BASE, "reports")
os.makedirs(OUT, exist_ok=True)
RNG = np.random.default_rng(20261119)


def load():
    conn = sqlite3.connect(DB)
    rows = conn.execute("""
        WITH last_day AS (SELECT MAX(date(invoice_date)) AS d FROM transactions),
        agg AS (
            SELECT customer_id,
                   MAX(date(invoice_date)) AS last_buy,
                   COUNT(DISTINCT invoice_no) AS freq,
                   SUM(amount) AS money,
                   SUM(amount) / COUNT(DISTINCT invoice_no) AS aov
            FROM transactions GROUP BY customer_id
        )
        SELECT customer_id, freq, money, aov,
               CAST(julianday((SELECT d FROM last_day)) - julianday(last_buy) AS INTEGER) AS recency
        FROM agg
    """).fetchall()
    conn.close()
    return rows


def split_groups(rows):
    rec = np.array([r[4] for r in rows])
    freq = np.array([r[1] for r in rows])
    money = np.array([r[2] for r in rows])
    aov = np.array([r[3] for r in rows])

    med_r, med_f, med_m = np.median(rec), np.median(freq), np.median(money)
    core = (rec <= med_r) & (freq >= med_f) & (money >= med_m)
    return aov[core], aov[~core], core.sum(), len(core)


def perm_test(a, b, iters=5000):
    obs = a.mean() - b.mean()
    pool = np.concatenate([a, b])
    n = len(a)
    diffs = np.empty(iters)
    for i in range(iters):
        RNG.shuffle(pool)
        diffs[i] = pool[:n].mean() - pool[n:].mean()
    p = float((np.abs(diffs) >= abs(obs)).mean())
    return float(obs), p


def boot_ci(a, b, iters=2000):
    diffs = np.empty(iters)
    for i in range(iters):
        diffs[i] = (RNG.choice(a, len(a), replace=True).mean()
                    - RNG.choice(b, len(b), replace=True).mean())
    return float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))


def cohens_d(a, b):
    na, nb = len(a), len(b)
    va, vb = a.var(ddof=1), b.var(ddof=1)
    pooled = np.sqrt(((na - 1) * va + (nb - 1) * vb) / (na + nb - 2))
    return float((a.mean() - b.mean()) / pooled)


def main():
    rows = load()
    core, other, n_core, n_all = split_groups(rows)
    diff, p = perm_test(core, other)
    lo, hi = boot_ci(core, other)
    d = cohens_d(core, other)

    lines = [
        "# 项目 C · 客户分层客单价差异的统计检验",
        "",
        f"> 数据：项目 A 的零售交易库（{n_all:,} 名客户）｜生成 2026-11-19",
        "",
        "## 问题",
        "",
        "核心客户（R 高、F 高、M 高）的**客单价**是否真的高于其他客户？还是随机波动？",
        "",
        "## 方法",
        "",
        "| 步骤 | 做法 |",
        "|---|---|",
        "| 分组 | 按 R/F/M 各自中位数切分，取「R 高 F 高 M 高」为核心组，其余为对照组 |",
        "| 检验 | 两独立样本**置换检验** 5,000 次：打乱分组标签，看观测均值差在随机分布里的位置 |",
        "| 区间 | **Bootstrap** 2,000 次重采样，给出均值差的 95% 置信区间 |",
        "| 效应量 | **Cohen's d**：差异相对于波动的量级 |",
        "",
        "## 结果",
        "",
        f"- 样本量：核心组 **{n_core:,}** 人，对照组 **{n_all - n_core:,}** 人",
        f"- 客单价均值差（核心 - 对照）：**{diff:.2f}**",
        f"- 置换检验 **p = {p:.4f}**（5,000 次）",
        f"- Bootstrap 95% 置信区间：**[{lo:.2f}, {hi:.2f}]**",
        f"- Cohen's d = **{d:.2f}**",
        "",
        "## 结论",
        "",
    ]
    if p < 0.05 and (lo > 0 or hi < 0):
        lines.append(f"差异**统计显著**：核心客户客单价均值高 {diff:.2f}，95% 置信区间不含 0，"
                     f"效应量 d={d:.2f}（{'小' if abs(d) < 0.2 else '中' if abs(d) < 0.8 else '大'}）。"
                     f"业务上可以认为分层有效，但幅度有限，行动上应优先做「频率」而非「单价」。")
    else:
        lines.append(f"差异**不显著**（p = {p:.4f}，置信区间 [{lo:.2f}, {hi:.2f}] 含 0）："
                     f"说明核心客户的优势主要体现在购买频次与总金额，而不是单笔客单价——"
                     f"这本身就是可讲的业务洞察：分层策略应打「复购频率」，不要指望涨价。")
    lines += [
        "",
        "## 面试怎么讲（1 分钟）",
        "",
        "> 我用置换检验验证了一个业务假设：核心客户和非核心客户的客单价有没有真实差异。"
        "置换检验不依赖正态假设，适合这种右偏的金额数据；我同时给了 bootstrap 置信区间和 Cohen's d，"
        "避免只看 p 值。结论是……（按上面结果说），所以运营策略应该打频次而不是单价。",
        "",
        "## 局限",
        "",
        "- 观察性数据，不是随机实验，只能说相关不能说因果；",
        "- 客单价右偏严重，均值敏感，报告里同时看中位数更稳；",
        "- 若要做真实验，需要对召回策略做 A/B 测试。",
    ]

    md = "\n".join(lines)
    open(os.path.join(OUT, "result.md"), "w", encoding="utf-8").write(md)
    json.dump({"n_core": int(n_core), "n_other": int(n_all - n_core), "diff": diff,
               "p_value": p, "ci95": [lo, hi], "cohens_d": d},
              open(os.path.join(OUT, "result.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(md)


if __name__ == "__main__":
    main()

