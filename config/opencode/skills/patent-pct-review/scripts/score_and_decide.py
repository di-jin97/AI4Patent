"""
score_and_decide.py — 读入含 total_score 的 reviews，按总分排序，取前 40% 进 PCT。
"""

import math
from copy import deepcopy


def score_and_decide(patents, target_ratio=0.40):
    n = len(patents)
    if n == 0:
        return []

    results = [deepcopy(p) for p in patents]

    # 按 total_score 从高到低排序
    sorted_results = sorted(results, key=lambda x: -x["total_score"])

    # 取前 40%，同分的都进
    cutoff_count = max(1, math.ceil(n * target_ratio))
    if cutoff_count < n:
        boundary = sorted_results[cutoff_count - 1]["total_score"]
        while cutoff_count < n and sorted_results[cutoff_count]["total_score"] == boundary:
            cutoff_count += 1

    for i, it in enumerate(sorted_results):
        it["final_decision"] = "进PCT" if i < cutoff_count else "不进PCT"
        it["rank"] = i + 1

    # 保持原输入顺序返回
    ref_to_result = {r["patent_ref"]: r for r in sorted_results}
    return [ref_to_result[p["patent_ref"]] for p in patents]


def summarize(results):
    n = len(results)
    n_in = sum(1 for r in results if r["final_decision"] == "进PCT")
    print(f"总专利数: {n}，进 PCT: {n_in} ({n_in/n*100:.1f}%)，不进: {n - n_in}")
    print()
    for r in sorted(results, key=lambda x: x["rank"]):
        print(f"  #{r['rank']:>3}  {r['patent_ref']:<30} 总分={r['total_score']:>5} → {r['final_decision']}")
