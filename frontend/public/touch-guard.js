// กันการ pinch-zoom ทั้งหน้าเว็บบนมือถือ (Editor ซูมเอกสารเอง) — แยกจาก index.html เพราะ CSP ไม่อนุญาต inline script
document.addEventListener("touchmove", function (e) {
  if (e.touches.length > 1) { e.preventDefault(); }
}, { passive: false });
