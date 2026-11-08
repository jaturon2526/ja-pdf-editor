---
name: pdf-editor-dev-guide
description: >-
  Use this skill whenever building, running, or developing features for the PDF Editor fullstack application. It contains essential build commands, Docker instructions, and PyMuPDF/Backend session gotchas.
---

# PDF Editor Development Guide

## 1. Build and Run Commands
> [!WARNING]
> **NO VOLUME MOUNT FOR BACKEND CODE.** The `docker-compose.yml` does *not* mount the local `./backend` directory into the `backend` container. **Any** modification to Python code requires a full rebuild. NEVER suggest `docker compose restart backend` for code changes.

When the user asks to build or restart the application, use these exact commands:

- **Rebuild Backend Only:**
  `docker compose up -d --build backend`
- **Rebuild Frontend Only:**
  `cd frontend && npm run build && cd .. && docker compose up -d --build frontend`
- **Rebuild Both:**
  `docker compose up -d --build backend`
  `cd frontend && npm run build && cd .. && docker compose up -d --build frontend`

## 2. Backend Conventions (อัปเดต ต.ค. 2026)
- **Auth + ownership on every session route:** any endpoint with `{session_id}` MUST take `session: PDFSession = Depends(get_owned_session)` (from `app.api.deps`). Never call `session_manager.get()` directly in a route. Non-owners get 404.
- **Creating sessions:** always pass `user_id=current_user.id` to `create_session_from_upload()` / `merge_pdfs()`.
- **`/pdf` routes live in `app/api/pdf/`** (`files.py`, `document.py`, `pages.py`, `redact.py`) — there is no `routes_pdf.py` anymore.
- **Heavy PyMuPDF work in `async def` routes** must run via `run_in_threadpool` under `session.lock` (see `app/api/pdf/redact.py`).
- **DB schema changes:** edit `app/models/domain.py`, then `alembic revision --autogenerate -m "..."` in `backend/`. Migrations run automatically on startup. Never use `create_all` or ad-hoc SQL.
- **Secrets:** JWT secret comes from `JWT_SECRET` or `SECRET_KEY`; `APP_ENV=production` refuses to start without a strong one.
- **Tests:** `cd backend && pytest -q` (SQLite, no Docker needed); frontend `npm run lint && npm test`.
- **Frontend file downloads:** session endpoints need the `Authorization` header, so never `window.open(url)` or `<img src=url>` them — use `api.downloadPdf`, `api.exportPages`, `api.fetchPdfBlob`, `api.fetchImageRawObjectUrl`.
- **Gemini:** use `app.services.gemini_client` (`generate_text(api_key, model, contents)`, `latest_flash_model(api_key)`) — package `google-genai`. Never import `google.generativeai` or call any global `configure()`: keys must stay per-request (user BYOK vs system key).
- **`pdf_service` is a package** (`app/services/pdf_service/`: core, pages, optimize, redact, properties, ocr). Import from `app.services.pdf_service` (the `__init__` re-exports); add new functions to the matching submodule and export them.
- **`edit_service` is a package too** (`app/services/edit_service/`: layout, text, images, watermark). Callers keep using `from app.services import edit_service`; design notes and bug history live in `edit_service/NOTES.md`.
- **Editor page structure:** `pages/Editor.jsx` wires hooks together. Undo/redo and every server-side document change go through `hooks/useDocumentHistory.js` (`runDocumentChange(action, {busy, success, failure})` enables Undo, clears drafts and refreshes); saving pending text/image edits is `hooks/useApplyEdits.js`; top menus are built in `components/editor/editorMenus.js`; Esc handling is `hooks/useEscapeStack.js` (ordered top-most first).
- **ESLint 10:** `eslint-plugin-react` still declares a peer of ESLint ≤9, so `package.json` has an `overrides` entry to accept ESLint 10. If `npm install` crashes with `edgesOut`, regenerate the lockfile with `npm install --legacy-peer-deps`; `npm ci` must then pass without flags.
- **Sequential signing** (`services/signing_service.py` workflow/DB, `services/signing_pdf.py` pyHanko, `api/routes_signing.py`): all signature fields are created up front when the request is sent (`SR{id}_S{order}`); signers only sign their own field, always incrementally. Electronic signatures in this flow are real PAdES signatures made with the system seal certificate (`UPLOAD_DIR/_signing/_seal/`), never page-content edits. Files live in `UPLOAD_DIR/_signing/{id}/v{n}.pdf` — never compact or rewrite them. Opening a PDF that already has digital signatures sets `session.signed_pdf_bytes`, and `get_download_path` skips compaction for such files.
- **Signing phase 3:** `SigningStep.order` is the unique list position (field name `SR{id}_S{order}`), `SigningStep.stage` is the signing round — steps with the same stage sign in parallel and `SigningRequest.current_order` holds the current *stage*. Use `signing_service.pending_steps(request)` / `my_step(...)`, never `order == current_order`. `signer_user_id` may be NULL for an invite (`invite_email`); `claim_invites` links it on login (verified accounts only) — always handle `step.signer is None`. Field boxes are stored in *displayed* (rotated) page coordinates; `signing_pdf` converts them with `derotation_matrix * ~transformation_matrix` and pre-rotates the stamp image. The evidence certificate (`signing_evidence.py`) is a separate system-sealed PDF — never append pages to a signed document. Sign through `signing_pdf.sign_with_optional_tsa(...)` so `SIGNING_TSA_URL` timestamps are applied (falls back to no timestamp if the TSA fails); tests swap `signing_pdf._timestamper` for a `DummyTimeStamper`. Signature stamp images are RGBA with a transparent background. The system seal comes from `SIGNING_SEAL_P12` (+`_PASSWORD`, a CA-issued .p12 mounted read-only from `backend/secrets/` at `/run/secrets/pdf-editor`) or falls back to the auto-generated self-signed cert when unset; a configured but unreadable .p12 must fail loudly, never fall back. Check it with `python -m scripts.seal_info`.
- **Signing notifications (phase 2):** always notify through `signing_service._notify(...)` and finish with `_commit(db)` — it commits first, then sends queued emails (`signing_emails.flush` → `mailer.send`, background thread). Never send mail before the commit. Email kinds are listed in `signing_emails.EMAIL_KINDS` (`sign_progress` is in-app only); users can opt out (`User.signing_email_notifications`). From is always the system address, display name "X ผ่าน APP_NAME", Reply-To = the actor. Without SMTP credentials mail is logged as `[EMAIL SIMULATION]`. Due-date reminders run in `main._periodic_signing_reminders` → `process_due_dates`, which claims each reminder with a conditional UPDATE so it is sent once even with several instances. Tests capture mail with `monkeypatch.setattr(mailer, "deliver", sent.append)`.
- **User font files are private:** `/edit/fonts/{key}/file` serves non-global fonts only with a valid `?t=` token (`make_resource_token`/`verify_resource_token` in `core/security.py`). The frontend must use `font.file_url` from the API, never build the URL itself for user fonts.
- **PDF→Word modes:** `mode="editable"` (pdf2docx + fixes, may use AI quota) and `mode="layout"` (`services/layout_docx.py`: text-free background image + positioned text frames, no AI quota).
- **Printing:** `GET /pdf/{id}/print?layout=as_shown` (`build_print_pdf`) bakes annotations, removes `/Rotate` and places pages on portrait sheets so printers can't auto-rotate them upside-down. The editor offers it when any page is landscape.
- **Pydantic v2 only:** use `model_config = ConfigDict(from_attributes=True)`, never `class Config`.
- **E2E tests:** `python -m scripts.create_test_user e2e@example.com 'E2e-Passw0rd!'` in backend, then `cd frontend && npx playwright install chromium && E2E_BASE_URL=http://localhost:8080 npm run test:e2e`. Frontend needs Node 22; install with `npm ci`.
- **CI (`.github/workflows/ci.yml`):** every PR and push to main runs backend pytest, frontend lint/test/build, then E2E against `docker-compose.dev.yml` (no `.env` files in CI — keep the stack bootable without them). If you add a test-only dependency or a new required env var, update the workflow too.
- **No more `patch_*.py` scripts at repo root** — edit source files directly. Old ones are in `archive/`.

## 3. Backend PDF Session Gotchas (CRITICAL)
- **Modifying a PDF:** NEVER use a context manager like `with session.modify_pdf()`. Instead, always do:
  ```python
  doc = require_unlocked(session)
  # ... modify doc ...
  session.mark_dirty() # Essential for saving to disk
  session.push_history() # Essential for undo/redo
  ```
- **History on All Edit Endpoints:** Every mutating endpoint in `routes_edit.py` (`delete_image`, `edit_text`, `replace_image`, `reposition_image`, `insert_image`) MUST call `session.push_history()` immediately after the service call. If missed, `session.history` will not record the state and Ctrl+Z (Undo) will not work.
- **File Loading:** When creating a new session from bytes (e.g. DOCX conversion or Merging files), use `pdf_service.create_session_from_upload(pdf_bytes, filename)`. If merging manually, ALWAYS remember to call `_try_open(session)` before returning so the file is loaded into memory, otherwise `require_unlocked` will throw an error.
- **Replacing the Working Document (Ghostscript/External Tools):** If a tool generates a completely new PDF file (e.g., Ghostscript output to a temp file), you CANNOT simply point `session.doc` to the temp file. `push_history()` strictly reads from `session.working_path`. You MUST:
  ```python
  import shutil
  session.doc.close()
  shutil.copy2(temp_out_path, session.working_path)
  session.doc = fitz.open(session.working_path)
  session.mark_dirty() # Crucial to trigger push_history
  ```

## 4. PyMuPDF (`fitz`) Gotchas
- **Image Deletion (Use Redaction, Not `delete_image`):** `page.delete_image(xref)` only deletes the object reference but leaves the drawing operator (`/Do`) in the content stream; the image still renders. The ONLY reliable method to completely remove an image from both content stream and output is:
  ```python
  annot = page.add_redact_annot(image_rect)
  page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_REMOVE)
  ```
- **Duplicate Image XREFs on a Single Page:** In PDF files, multiple graphics/icons/lines frequently share the exact same `xref`.
  - Backend `delete_image` should accept `rect: Optional[Rect]` to target the exact instance rather than blindly deleting the first matching `xref`.
  - `get_images` should assign a unique instance ID (e.g. `img-{xref}-{idx}`).
- **Arbitrary Rotation:** `page.insert_text(..., rotate=angle)` ONLY accepts integer multiples of 90 (0, 90, 180, 270). If you need an arbitrary angle (e.g. 45 degrees for a watermark), you MUST use the `morph` parameter:
  ```python
  morph = (point, fitz.Matrix(-angle))
  page.insert_text(point, text, ..., morph=morph)
  ```
- **Thai Fonts:** `insert_text` with default fonts will not render Thai characters. Always use the bundled `Sarabun-Regular.ttf` retrieved via `fonts.resolve_font_path("sarabun")[1]`.
- **Flattening with Ghostscript & Thai Fonts (The Dot Bug):** PyMuPDF generates `.....` for missing Thai glyphs when `annot.update()` is called or when Ghostscript reads the `content` field. In this app, `text_note` and `rect` text are *already* drawn as images onto the page by Pillow. The `Annot` object is just an invisible overlay. 
  - Before feeding a PDF to Ghostscript to flatten, you MUST delete `FreeText` and `Square` annotations (`page.delete_annot(annot)`) so Ghostscript doesn't render dots.
  - Keep `Highlight` annotations but force their Print flag (`annot.set_flags(annot.flags | 4)`).
  - After Ghostscript runs, loop through the output and delete all remaining floating annotations again to prevent "double text/shadows".

## 5. LibreOffice Headless
- The backend Dockerfile must contain `libreoffice-writer`, `libreoffice-calc`, `libreoffice-impress`, and `default-jre-headless`.
- Convert files via `subprocess.run(["libreoffice", "--headless", "--convert-to", "pdf", ...])`.

## 6. Auto-Gen, UI, and Batch Processing Gotchas
- **React JSX Syntax:** When displaying Jinja2 syntax like `{{ ... }}` on the UI (common for docxtpl templates), you MUST escape it as `{'{{ ... }}'}`. Unescaped curly braces will be parsed as an object literal, causing a fatal syntax error and a white screen.
- **docxcompose Page Breaks:** `Composer.append()` appends content immediately after the last paragraph of the previous document. To start on a new page, you MUST explicitly call `composer.doc.add_page_break()` before appending.
- **Jinja2 Rendering:** Always use kwargs unpacking when rendering a dictionary: `Template.render(**context)`.
- **Parallel Array Safety:** In batch processing loops with `try...except`, always append to parallel tracking arrays (e.g., `rendered_docs` and `base_names`) atomically at the VERY END of the `try` block. If an exception occurs halfway, this prevents the arrays from becoming out of sync (which leads to `IndexError` later).
- **Image Editing Unique Keys in React:** NEVER key images solely by `img-${img.xref}` in React state (`pendingImageEdits`) or component keys. If a page has 5 instances of `xref: 101`, duplicate keys corrupt React reconciliation, cause masks to stack or fail to unmount, and break restore. Always use a unique instance key (`img.id || img-${img.xref}-${idx}`).
- **Pointer Events on Canvas Masks:** `.image-edit-original-mask` has `pointer-events: none`. Any child or clickable overlay (like `.deleted-mask` or restore buttons) MUST set `pointer-events: auto !important` and `onPointerDown={(e) => e.stopPropagation()}` to prevent the canvas `onPointerDown` handler from capturing clicks.
- **Editor `touchedPages` Set:** After saving edits in `Editor.jsx`, pages only re-render if present in `touchedPages`. Every delete task must call `touchedPages.add(pageNumber)`.
