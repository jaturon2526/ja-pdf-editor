# ---------- stage 1: build ----------
FROM docker.io/library/python:3.11.10-slim-bookworm AS build
WORKDIR /app
COPY requirements.txt .
RUN apt-get update && apt-get install -y --no-install-recommends gcc g++ python3-dev && \
    python -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

# ---------- stage 1b: Ghostscript ----------
# Debian bookworm มี Ghostscript 10.0.0 (2022) — คอมไพล์รุ่นใหม่เอง: แก้ช่องโหว่หลายตัว (Ghostscript อ่าน PDF ที่ผู้ใช้
# อัปโหลด) และรองรับ -dPreserveMarkedContent ที่ใช้คงข้อความไทยของ PDF จาก Word/LibreOffice ตอนลดขนาด/PDF/A
# ไบนารีลิงก์ไลบรารีที่มากับซอร์สแบบ static (พึ่งแค่ libc) และฝังไฟล์ init/ฟอนต์ไว้ในตัว — คัดลอกไป stage final ได้ทันที
# layer นี้ cache ไว้ตราบที่ GS_VERSION ไม่เปลี่ยน (build ครั้งแรกราว 5–10 นาที)
FROM docker.io/library/python:3.11.10-slim-bookworm AS ghostscript
ARG GS_VERSION=10.06.0
ARG GS_SHA256=64352648c2c081c8a9fb1a12dc1965e01ead7c57f58b72d1b54f6ef1cef3c561
RUN apt-get update && apt-get install -y --no-install-recommends build-essential curl ca-certificates xz-utils && \
    rm -rf /var/lib/apt/lists/*
RUN set -eux; \
    tag="gs$(echo "$GS_VERSION" | tr -d .)"; \
    curl -fsSL --retry 3 -o /tmp/gs.tar.xz \
      "https://github.com/ArtifexSoftware/ghostpdl-downloads/releases/download/${tag}/ghostscript-${GS_VERSION}.tar.xz"; \
    echo "${GS_SHA256}  /tmp/gs.tar.xz" | sha256sum -c -; \
    tar -xJf /tmp/gs.tar.xz -C /tmp; \
    cd "/tmp/ghostscript-${GS_VERSION}"; \
    ./configure --prefix=/opt/ghostscript --without-x --disable-cups --disable-dbus --disable-gtk \
      --without-libidn --without-libpaper --without-tesseract --disable-fontconfig --with-drivers=pdfwrite; \
    make -j"$(nproc)"; \
    make install; \
    rm -rf /opt/ghostscript/share/man /tmp/gs.tar.xz "/tmp/ghostscript-${GS_VERSION}"; \
    /opt/ghostscript/bin/gs --version

# ---------- stage 2: final ----------
FROM docker.io/library/python:3.11.10-slim-bookworm AS final
WORKDIR /app

# ติดตั้งเฉพาะ Runtime Dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr tesseract-ocr-tha libreoffice-writer libreoffice-calc libreoffice-impress \
    default-jre-headless fonts-thai-tlwg fonts-urw-base35 \
    && rm -rf /var/lib/apt/lists/*

# Create explicit non-root user
RUN addgroup --gid 10000 appgroup && \
    adduser --uid 10000 --gid 10000 --shell /bin/sh --disabled-password appuser

COPY --from=build /opt/venv /opt/venv
COPY --from=ghostscript /opt/ghostscript /opt/ghostscript
ENV PATH="/opt/ghostscript/bin:/opt/venv/bin:$PATH"

COPY app ./app
# สคริปต์ดูแลระบบ เช่น `python -m scripts.create_test_user` (ใช้ใน E2E/CI)
COPY scripts ./scripts
# ไฟล์ตัวอย่างเอกสารอัตโนมัติ — ดาวน์โหลดจากหน้าคู่มือ (GET /autogen/samples/{name})
COPY sample_autogen ./sample_autogen

# Handle fonts and update fontconfig cache
RUN mkdir -p /usr/local/share/fonts/pdf-editor && \
    cp /app/app/assets/fonts/*.ttf /usr/local/share/fonts/pdf-editor/ 2>/dev/null || true && \
    fc-cache -fv /usr/local/share/fonts/pdf-editor

# กำหนดสิทธิ์ให้ non-root เข้าถึง Directory ที่จำเป็น
ENV PDF_UPLOAD_DIR=/data/uploads \
    PDF_WORKING_DIR=/data/working
RUN mkdir -p /data/uploads /data/working /data/trusted_certs /tmp && \
    chown -R appuser:appgroup /app /data /tmp /usr/local/share/fonts/pdf-editor

EXPOSE 8000
USER 10000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health', timeout=3).status == 200 else 1)"

# BACKEND_WORKERS = จำนวน process (ใช้ CPU หลาย core — งาน PDF ใน Python ใช้ได้ทีละ core ต่อ process) · ไม่ตั้ง = 1
# หลาย worker ต้องมี Redis (PDF_REDIS_URL) — session ของเอกสาร/ล็อก/งานเบื้องหลังแชร์กันผ่าน Redis
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${BACKEND_WORKERS:-1}"]
