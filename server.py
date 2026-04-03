from fastmcp import FastMCP
import sqlite3
import os

# 数据库路径使用绝对路径，避免因工作目录不同导致找不到文件
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sales.db")

# 1. 初始化 MCP 服务
mcp = FastMCP("Sales Data Server")


# 2. 定义工具：查询所有产品列表
@mcp.tool()
def list_products() -> str:
    """
    查询数据库中所有已有的产品名称列表。
    适用于用户询问"有哪些产品"、"都卖什么"等情况。

    返回：
        str: 产品列表文本
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT DISTINCT product_name FROM sales_records ORDER BY product_name")
        products = [row[0] for row in c.fetchall()]
        conn.close()

        if products:
            report = "📦 **产品列表**\n"
            for i, name in enumerate(products, 1):
                report += f"  {i}. {name}\n"
            report += f"\n共 {len(products)} 个产品"
            return report
        else:
            return "暂无产品数据"

    except Exception as e:
        return f"查询出错：{str(e)}"


# 3. 定义工具：查询产品销售数据
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
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        # 先尝试精确匹配，再尝试忽略空格的模糊匹配
        c.execute("SELECT region, amount, sale_date FROM sales_records WHERE product_name=?",
                  (product_name,))
        rows = c.fetchall()

        # 精确匹配无结果时，去掉空格做模糊匹配
        if not rows:
            no_space = product_name.replace(" ", "")
            c.execute(
                "SELECT region, amount, sale_date FROM sales_records "
                "WHERE REPLACE(product_name, ' ', '')=?",
                (no_space,),
            )
            rows = c.fetchall()

        # 计算总额（使用上一步命中的行）
        if rows:
            total_amount = sum(row[1] for row in rows)
        else:
            total_amount = 0

        conn.close()

        if rows:
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
        return f"查询出错：{str(e)}"


# 4. 启动服务
if __name__ == "__main__":
    mcp.run()