from fastmcp import FastMCP
import sqlite3
import os
from contextlib import contextmanager
from typing import Generator

# 数据库路径使用绝对路径，避免因工作目录不同导致找不到文件
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "object_db", "sales.db")

# 1. 初始化 MCP 服务
mcp = FastMCP("Sales Data Server")


# ─────────────────────────────────────────────
#  辅助函数
# ─────────────────────────────────────────────

def _get_connection():
    """获取数据库连接"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def _get_db_cursor() -> Generator[sqlite3.Cursor, None, None]:
    """
    数据库连接上下文管理器，确保连接正确关闭。
    自动提交成功事务，失败时回滚。
    """
    conn = None
    try:
        conn = _get_connection()
        cursor = conn.cursor()
        yield cursor
        conn.commit()
    except Exception as e:
        if conn:
            conn.rollback()
        raise RuntimeError(f"数据库操作失败: {e}") from e
    finally:
        if conn:
            conn.close()


def _escape_like_pattern(pattern: str) -> str:
    """
    转义 SQL LIKE 查询中的特殊字符，防止注入。
    
    LIKE 查询中的特殊字符：
    - %: 匹配任意字符
    - _: 匹配单个字符
    """
    return pattern.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _rows_to_dicts(rows):
    """将 sqlite3.Row 转为普通字典列表"""
    return [dict(row) for row in rows]


# ─────────────────────────────────────────────
#  工具：查询所有产品列表
# ─────────────────────────────────────────────

@mcp.tool()
def list_products() -> str:
    """
    查询数据库中所有已有的产品名称列表。
    适用于用户询问"有哪些产品"、"都卖什么"等情况。

    返回：
        str: 产品列表文本
    """
    try:
        with _get_db_cursor() as c:
            c.execute("SELECT DISTINCT product_name FROM sales_records ORDER BY product_name")
            products = [row[0] for row in c.fetchall()]

        if products:
            report = "📦 **产品列表**\n"
            for i, name in enumerate(products, 1):
                report += f"  {i}. {name}\n"
            report += f"\n共 {len(products)} 个产品"
            return report
        else:
            return "暂无产品数据"

    except Exception as e:
        return f"⚠️ 查询出错：{str(e)}"


# ─────────────────────────────────────────────
#  工具：按产品查询销售数据
# ─────────────────────────────────────────────

@mcp.tool()
def query_sales_by_product(product_name: str) -> str:
    """
    查询指定产品的销售记录汇总。
    适用于用户询问某产品的销量、销售额或市场表现时。

    参数：
        product_name (str): 产品名称，例如 'AI 助手专业版'

    返回：
        str: 包含各地区销售金额总和及记录条数的文本报告
    """
    if not product_name or not product_name.strip():
        return "⚠️ 产品名称不能为空"
    
    # 输入验证：限制长度防止滥用
    product_name = product_name.strip()[:100]
    
    try:
        with _get_db_cursor() as c:
            # 先尝试精确匹配
            c.execute(
                "SELECT region, amount, sale_date FROM sales_records WHERE product_name=?",
                (product_name,)
            )
            rows = c.fetchall()

            # 精确匹配无结果时，去掉空格做模糊匹配
            if not rows:
                no_space = product_name.replace(" ", "")
                c.execute(
                    "SELECT region, amount, sale_date FROM sales_records "
                    "WHERE REPLACE(product_name, ' ', '')=?",
                    (no_space,)
                )
                rows = c.fetchall()

        if rows:
            total_amount = sum(row[1] for row in rows)
            report = f"📊 **{product_name} 销售简报**\n"
            report += f"总销售额：¥{total_amount:,.2f}\n"
            report += f"成交笔数：{len(rows)}\n\n"
            report += "**明细**:\n"
            for region, amount, date in rows:
                report += f"- {date} | {region} | ¥{amount:,.2f}\n"
            return report
        else:
            return f"未找到产品 '{product_name}' 的销售记录"

    except Exception as e:
        return f"⚠️ 查询出错：{str(e)}"


# ─────────────────────────────────────────────
#  工具：按区域查询销售数据
# ─────────────────────────────────────────────

@mcp.tool()
def query_sales_by_region(region: str) -> str:
    """
    查询指定区域的销售记录汇总。
    适用于用户询问某区域的销售表现、业绩情况时。

    参数：
        region (str): 区域名称，例如 '华东'、'华北'

    返回：
        str: 包含该区域各产品销售情况的文本报告
    """
    if not region or not region.strip():
        return "⚠️ 区域名称不能为空"
    
    # 输入验证：限制长度防止滥用
    region = region.strip()[:50]
    
    try:
        with _get_db_cursor() as c:
            # 先尝试精确匹配
            c.execute(
                "SELECT product_name, amount, sale_date FROM sales_records WHERE region=?",
                (region,)
            )
            rows = c.fetchall()

            # 精确匹配无结果时，使用安全的模糊匹配
            if not rows:
                safe_region = _escape_like_pattern(region)
                c.execute(
                    "SELECT product_name, amount, sale_date FROM sales_records "
                    "WHERE region LIKE ? ESCAPE '\\'",
                    (f"%{safe_region}%",)
                )
                rows = c.fetchall()

        if rows:
            total_amount = sum(row[1] for row in rows)
            report = f"📊 **{region} 区域销售简报**\n"
            report += f"总销售额：¥{total_amount:,.2f}\n"
            report += f"成交笔数：{len(rows)}\n\n"
            report += "**明细**:\n"
            for product, amount, date in rows:
                report += f"- {date} | {product} | ¥{amount:,.2f}\n"
            return report
        else:
            return f"未找到区域 '{region}' 的销售记录"

    except Exception as e:
        return f"⚠️ 查询出错：{str(e)}"


# ─────────────────────────────────────────────
#  工具：销售全局概览
# ─────────────────────────────────────────────

@mcp.tool()
def get_sales_overview() -> str:
    """
    获取所有销售数据的全局概览，包括总销售额、总笔数、各区域汇总、各产品汇总。
    适用于用户询问"整体情况"、"销售概览"、"整体表现"时。

    返回：
        str: 全局销售概览报告
    """
    try:
        with _get_db_cursor() as c:
            # 总额和笔数
            c.execute("SELECT COUNT(*), SUM(amount) FROM sales_records")
            total_orders, total_amount = c.fetchone()
            total_amount = total_amount or 0
            avg_price = total_amount / total_orders if total_orders > 0 else 0

            # 各区域汇总
            c.execute(
                "SELECT region, COUNT(*) as cnt, SUM(amount) as total "
                "FROM sales_records GROUP BY region ORDER BY total DESC"
            )
            region_rows = c.fetchall()

            # 各产品汇总
            c.execute(
                "SELECT product_name, COUNT(*) as cnt, SUM(amount) as total "
                "FROM sales_records GROUP BY product_name ORDER BY total DESC"
            )
            product_rows = c.fetchall()

        report = "📊 **销售全局概览**\n\n"
        report += f"**核心指标**\n"
        report += f"- 总销售额：¥{total_amount:,.2f}\n"
        report += f"- 成交笔数：{total_orders}\n"
        report += f"- 平均客单价：¥{avg_price:,.2f}\n\n"

        report += "**各区域汇总**\n"
        for region, cnt, total in region_rows:
            pct = (total / total_amount * 100) if total_amount > 0 else 0
            report += f"- {region}：¥{total:,.2f}（{cnt}笔，{pct:.1f}%）\n"

        report += "\n**各产品汇总**\n"
        for product, cnt, total in product_rows:
            pct = (total / total_amount * 100) if total_amount > 0 else 0
            report += f"- {product}：¥{total:,.2f}（{cnt}笔，{pct:.1f}%）\n"

        return report

    except Exception as e:
        return f"⚠️ 查询出错：{str(e)}"


# ─────────────────────────────────────────────
#  工具：获取原始数据（供脚本分析用）
# ─────────────────────────────────────────────

@mcp.tool()
def get_raw_sales_data(product_name: str | None = None, region: str | None = None) -> str:
    """
    获取原始销售记录数据（JSON 格式），供后续分析脚本使用。
    可按产品或区域筛选。返回结构化 JSON，包含所有字段。

    参数：
        product_name (str, 可选): 产品名称筛选
        region (str, 可选): 区域名称筛选

    返回：
        str: JSON 格式的销售记录列表
    """
    try:
        import json

        # 输入验证
        if product_name:
            product_name = product_name.strip()[:100]
        if region:
            region = region.strip()[:50]

        with _get_db_cursor() as c:
            sql = "SELECT product_name, region, amount, sale_date FROM sales_records WHERE 1=1"
            params = []

            if product_name:
                sql += " AND product_name=?"
                params.append(product_name)

            if region:
                sql += " AND region=?"
                params.append(region)

            sql += " ORDER BY sale_date"
            c.execute(sql, params)
            rows = _rows_to_dicts(c.fetchall())

        return json.dumps(rows, ensure_ascii=False)

    except Exception as e:
        import json
        return json.dumps({"error": f"查询失败: {str(e)}"})


# ─────────────────────────────────────────────
#  启动服务
# ─────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run()
