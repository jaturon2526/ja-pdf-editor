import csv
from docx import Document
import openpyxl

# 1. Create CSV
csv_data = [
    ["customer_name", "invoice_no", "total_amount"],
    ["คุณ สมชาย ใจดี", "INV-001", "1,500.00"],
    ["บริษัท เอบีซี จำกัด", "INV-002", "25,000.00"]
]
with open('sample_autogen/data_flat.csv', 'w', newline='', encoding='utf-8-sig') as f:
    writer = csv.writer(f)
    writer.writerows(csv_data)

# 2. Create XLSX
wb = openpyxl.Workbook()
ws = wb.active
ws.title = "Data"
for row in csv_data:
    ws.append(row)
wb.save('sample_autogen/data_flat.xlsx')

# 3. Create DOCX Template for Flat Data
doc = Document()
doc.add_heading('หนังสือทวงถามหนี้', 0)
p = doc.add_paragraph()
p.add_run('เรียน: ').bold = True
p.add_run('{{ customer_name }}\n')
p.add_run('อ้างถึงใบแจ้งหนี้เลขที่: ').bold = True
p.add_run('{{ invoice_no }}\n\n')

doc.add_paragraph('ตามที่ท่านได้สั่งซื้อสินค้าและมียอดค้างชำระ จำนวนเงินทั้งสิ้น {{ total_amount }} บาท '
                  'ทางเราขอให้ท่านโปรดชำระเงินภายใน 7 วัน นับจากวันที่ได้รับจดหมายฉบับนี้')
doc.save('sample_autogen/template_flat.docx')

print("Flat samples created.")
