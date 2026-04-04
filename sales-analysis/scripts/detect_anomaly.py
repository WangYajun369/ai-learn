#!/usr/bin/env python3
"""
销售异常检测脚本
输入：JSON 格式的销售记录列表
输出：JSON 格式的异常检测结果
"""

import json
import sys
from collections import defaultdict


def detect_anomalies(records: list[dict]) -> dict:
    """
    检测销售数据中的异常点。

    参数:
        records: [{"region": str, "amount": float, "sale_date": str, "product_name": str}, ...]

    返回:
        dict: 异常检测结果
    """
    anomalies = []

    if not records:
        return {"anomalies": [], "summary": "无数据可分析"}

    # 1. 单笔金额异常检测（超过均值 3 倍标准差）
    amounts = [r["amount"] for r in records]
    mean_amt = sum(amounts) / len(amounts)
    variance = sum((a - mean_amt) ** 2 for a in amounts) / len(amounts)
    std_amt = variance ** 0.5

    if std_amt > 0:
        for r in records:
            z_score = (r["amount"] - mean_amt) / std_amt
            if abs(z_score) > 3:
                anomalies.append({
                    "type": "outlier",
                    "severity": "high" if abs(z_score) > 4 else "medium",
                    "message": f"异常金额：{r['sale_date']} {r['region']} ¥{r['amount']:,.2f}（Z-score: {z_score:.1f}）",
                    "record": r,
                })

    # 2. 区域间差异检测（某区域均值超过整体均值 2 倍）
    region_amounts = defaultdict(list)
    for r in records:
        region_amounts[r["region"]].append(r["amount"])

    for region, amounts in region_amounts.items():
        region_mean = sum(amounts) / len(amounts)
        if mean_amt > 0 and region_mean > mean_amt * 2:
            anomalies.append({
                "type": "region_gap",
                "severity": "medium",
                "message": f"区域差异：{region} 平均单笔 ¥{region_mean:,.2f}，为整体均值（¥{mean_amt:,.2f}）的 {region_mean/mean_amt:.1f} 倍",
            })

    # 3. 时间趋势异常检测（相邻月份波动超过 100%）
    monthly_amounts = defaultdict(float)
    for r in records:
        month = r["sale_date"][:7]
        monthly_amounts[month] += r["amount"]

    months_sorted = sorted(monthly_amounts.keys())
    for i in range(1, len(months_sorted)):
        prev = monthly_amounts[months_sorted[i - 1]]
        curr = monthly_amounts[months_sorted[i]]
        if prev > 0:
            change = abs(curr - prev) / prev * 100
            if change > 100:
                anomalies.append({
                    "type": "volatility",
                    "severity": "high",
                    "message": f"月度剧烈波动：{months_sorted[i-1]} → {months_sorted[i]} 变化 {change:.1f}%",
                })

    # 4. 生成总结
    severity_counts = defaultdict(int)
    for a in anomalies:
        severity_counts[a["severity"]] += 1

    summary = f"共检测到 {len(anomalies)} 个异常"
    if severity_counts.get("high", 0) > 0:
        summary += f"（其中 {severity_counts['high']} 个高风险）"

    return {
        "anomalies": anomalies,
        "summary": summary,
        "high_count": severity_counts.get("high", 0),
        "medium_count": severity_counts.get("medium", 0),
    }


if __name__ == "__main__":
    input_text = sys.stdin.read()
    try:
        records = json.loads(input_text)
        result = detect_anomalies(records)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"JSON 解析失败：{e}"}))
    except Exception as e:
        print(json.dumps({"error": f"检测异常：{e}"}))
