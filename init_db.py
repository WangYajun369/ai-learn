import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sales.db")
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS sales_records
             (id INTEGER PRIMARY KEY, product_name TEXT,
              region TEXT, amount REAL, sale_date TEXT)''')
data = [
    (1, 'AI 助手专业版', '华北', 15000.0, '2024-05-01'),
    (2, 'AI 助手企业版', '华东', 50000.0, '2024-05-02'),
    (3, 'AI 助手专业版', '华南', 12000.0, '2024-05-03'),
]
c.executemany("INSERT OR IGNORE INTO sales_records VALUES (?, ?, ?, ?, ?)", data)
conn.commit()
conn.close()
print("✅ 销售测试数据库已生成")