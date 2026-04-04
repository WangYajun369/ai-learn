#!/usr/bin/env python3
"""
销售数据指标计算脚本
输入：JSON 格式的销售记录列表
输出：JSON 格式的分析结果（增长率、异常标记等）
"""

import json
import sys
from collections import defaultdict


def calculate_metrics(records: list[dict]) -> dict:
    """
    计算销售核心指标和异常标记。

    参数:
        records: [{"region": str, "amount": float, "sale_date": str, "product_name": str}, ...]

    返回:
        dict: 分析结果
    """
    if not records:
        return {"error": "无数据", "total_amount": 0, "total_orders": 0}

    # 基础指标
    total_amount = sum(r["amount"] for r in records)
    total_orders = len(records)
    avg_price = total_amount / total_orders if total_orders > 0 else 0

    # 区域分布
    region_amounts = defaultdict(float)
    region_counts = defaultdict(int)
    for r in records:
        region_amounts[r["region"]] += r["amount"]
        region_counts[r["region"]] += 1

    region_breakdown = []
    for region in sorted(region_amounts.keys()):
        amount = region_amounts[region]
        pct = (amount / total_amount * 100) if total_amount > 0 else 0
        region_breakdown.append({
            "region": region,
            "amount": round(amount, 2),
            "orders": region_counts[region],
            "percentage": round(pct, 1),
        })

    # 异常检测
    anomalies = []

    # 区域集中度检测
    for rb in region_breakdown:
        if rb["percentage"] > 50:
            anomalies.append({
                "type": "warning",
                "message": f"区域集中度偏高：{rb['region']} 占比 {rb['percentage']}%",
            })

    # 整体销售额检测
    if total_amount < 10000:
        anomalies.append({
            "type": "warning",
            "message": "整体销售额偏低，建议关注",
        })

    # 月度趋势分析
    monthly_amounts = defaultdict(float)
    for r in records:
        month = r["sale_date"][:7]  # YYYY-MM
        monthly_amounts[month] += r["amount"]

    months_sorted = sorted(monthly_amounts.keys())
    trend_analysis = []
    for i in range(1, len(months_sorted)):
        prev = monthly_amounts[months_sorted[i - 1]]
        curr = monthly_amounts[months_sorted[i]]
        if prev > 0:
            growth_rate = round((curr - prev) / prev * 100, 1)
            trend_label = ""
            if growth_rate > 50:
                trend_label = "🔥 高速增长"
            elif growth_rate < -20:
                trend_label = "📉 显著下滑"
            else:
                trend_label = "✅ 平稳运行"
            trend_analysis.append({
                "period": f"{months_sorted[i-1]} → {months_sorted[i]}",
                "growth_rate": growth_rate,
                "label": trend_label,
            })

    return {
        "total_amount": round(total_amount, 2),
        "total_orders": total_orders,
        "avg_price": round(avg_price, 2),
        "region_breakdown": region_breakdown,
        "anomalies": anomalies,
        "trend_analysis": trend_analysis,
        "monthly_amounts": {k: round(v, 2) for k, v in monthly_amounts.items()},
    }


if __name__ == "__main__":
    # 从 stdin 读取 JSON 数据
    input_text = sys.stdin.read()
    try:
        records = json.loads(input_text)
        result = calculate_metrics(records)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"JSON 解析失败：{e}"}))
    except Exception as e:
        print(json.dumps({"error": f"计算异常：{e}"}))
