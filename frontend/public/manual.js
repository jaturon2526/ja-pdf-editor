// รูปหน้าจอในคู่มือ — แยกเป็นไฟล์เพราะ Content-Security-Policy ไม่อนุญาต onload/onerror แบบ inline
//   data-manual-shot: โหลดได้ → แสดงรูปและซ่อนข้อความ 📸 ตัวแทนก่อนหน้า · ไม่มีไฟล์ → ซ่อนรูป (คงข้อความ)
//   data-hide-if-missing: ไม่มีไฟล์ → ซ่อนรูป
function watchImage(img, onShown) {
  function missing() { img.style.display = "none"; }
  if (img.complete) { if (img.naturalWidth > 0) onShown(); else missing(); return; }
  img.addEventListener("load", onShown);
  img.addEventListener("error", missing);
}
document.querySelectorAll("img[data-manual-shot]").forEach(function (img) {
  watchImage(img, function () {
    img.style.display = "block";
    if (img.previousElementSibling) img.previousElementSibling.style.display = "none";
  });
});
document.querySelectorAll("img[data-hide-if-missing]").forEach(function (img) {
  watchImage(img, function () {});
});
