import json
from docx import Document

data = [
  {
    "customer_name": "คุณ สมชาย ใจดี",
    "invoice_no": "INV-001",
    "purchases": [
      { "item": "โน้ตบุ๊ก", "qty": 1, "price": 25000 },
      { "item": "เมาส์ไร้สาย", "qty": 2, "price": 500 }
    ],
    "payments": [
      { "date": "10/09/2026", "method": "โอนเงิน", "amount": 10000 },
      { "date": "12/09/2026", "method": "เงินสด", "amount": 16000 }
    ]
  },
  {
    "customer_name": "คุณ สมศรี รักเรียน",
    "invoice_no": "INV-002",
    "purchases": [
      { "item": "คีย์บอร์ดแมคคานิคอล", "qty": 1, "price": 3500 },
      { "item": "จอภาพ 27 นิ้ว", "qty": 1, "price": 8900 }
    ],
    "payments": [
      { "date": "15/09/2026", "method": "บัตรเครดิต", "amount": 12400 }
    ]
  }
]

with open('sample_autogen/data.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

doc = Document()
doc.add_heading('ใบแจ้งหนี้ / Invoice', 0)

p = doc.add_paragraph()
p.add_run('ชื่อลูกค้า: ').bold = True
p.add_run('{{ customer_name }}\n')
p.add_run('เลขที่ใบแจ้งหนี้: ').bold = True
p.add_run('{{ invoice_no }}')

doc.add_heading('รายการสินค้าที่สั่งซื้อ', level=2)
table = doc.add_table(rows=1, cols=3)
table.style = 'Table Grid'
hdr_cells = table.rows[0].cells
hdr_cells[0].text = 'สินค้า'
hdr_cells[1].text = 'จำนวน'
hdr_cells[2].text = 'ราคา'

row_for = table.add_row().cells
row_for[0].text = '{%tr for p in purchases %}'

row_data = table.add_row().cells
row_data[0].text = '{{ p.item }}'
row_data[1].text = '{{ p.qty }}'
row_data[2].text = '{{ p.price }}'

row_endfor = table.add_row().cells
row_endfor[0].text = '{%tr endfor %}'

doc.add_page_break()

doc.add_heading('ประวัติการชำระเงิน', level=2)
table2 = doc.add_table(rows=1, cols=3)
table2.style = 'Table Grid'
hdr_cells2 = table2.rows[0].cells
hdr_cells2[0].text = 'วันที่'
hdr_cells2[1].text = 'ช่องทาง'
hdr_cells2[2].text = 'ยอดเงิน'

row_for2 = table2.add_row().cells
row_for2[0].text = '{%tr for pay in payments %}'

row_data2 = table2.add_row().cells
row_data2[0].text = '{{ pay.date }}'
row_data2[1].text = '{{ pay.method }}'
row_data2[2].text = '{{ pay.amount }}'

row_endfor2 = table2.add_row().cells
row_endfor2[0].text = '{%tr endfor %}'

doc.save('sample_autogen/template.docx')
print("Sample files generated in sample_autogen/")
