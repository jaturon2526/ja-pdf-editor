#!/bin/bash
echo "1. เริ่มรันระบบ Docker..."
docker compose up -d --build

echo "2. รอให้ระบบพร้อม (backend จะสร้าง/อัปเกรดตารางในฐานข้อมูลเองอัตโนมัติผ่าน Alembic ตอน start)..."
sleep 10

echo "3. เรียบร้อย! เปิดเว็บได้เลยที่ http://localhost:8080"
