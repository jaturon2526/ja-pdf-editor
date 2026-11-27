// เมนูบนสุดของหน้า Editor (ไฟล์ / แก้ไข / มุมมอง / ...) — แยกมาจาก Editor.jsx
// ฟังก์ชันล้วน: รับ state + handler แล้วคืนโครงสร้างเมนูให้ <MenuBar>

const FEEDBACK_FORM_URL =
  "https://docs.google.com/forms/d/e/1FAIpQLScPacKO8qkTy1nKWqVcBph5uZ0sfEKFoI1miugStIk7OyACpA/viewform?usp=header";

export function buildEditorMenus({
  t = (k) => k,
  session,
  activeTool,
  setActiveTool,
  canUndo,
  canRedo,
  isSidebarOpen,
  setIsSidebarOpen,
  goToDashboard,
  openCreateBlank,
  openOfficeDialog,
  openFileDialog,
  saveToServer,
  download,
  print,
  closeDocument,
  openExtract,
  openSaveCopy,
  undo,
  redo,
  openFind,
  zoomIn,
  zoomOut,
  setZoom,
  continuousMode,
  toggleContinuousMode,
  docPropsHook,
  signatureHook,
  openRedactSearch,
  runOcrLayer,
  openPii,
  openWatermark,
  openPageNumbers,
  openInsertPages,
  openBarcode,
  openStamp,
  insertImage,
  openCompress,
  openFlatten,
  openConvertWord,
  openCompare,
  openAbout,
}) {
  const noDoc = !session;
  const toggleTool = (tool) => () => setActiveTool(activeTool === tool ? null : tool);

  return [
    {
      label: t("editor.menu.file"),
      items: [
        { label: t("editor.menu.backToDashboard"), onClick: goToDashboard },
        { divider: true },
        { label: t("editor.menu.createBlank"), hint: t("editor.menu.createBlankHint"), onClick: openCreateBlank },
        { label: t("editor.menu.createFromOffice"), onClick: openOfficeDialog },
        { label: t("editor.menu.openFile"), shortcut: "Ctrl+O", onClick: openFileDialog },
        { divider: true },
        { label: t("editor.menu.saveOverwrite"), shortcut: "Ctrl+S", onClick: saveToServer, disabled: noDoc },
        { label: t("editor.menu.extractExport"), onClick: openExtract, disabled: noDoc },
        { label: t("editor.menu.saveCopy"), onClick: openSaveCopy, disabled: noDoc },
        { label: t("editor.menu.download"), onClick: download, disabled: noDoc },
        { label: t("editor.menu.print"), shortcut: "Ctrl+P", onClick: print, disabled: noDoc },
        { divider: true },
        session?.isPasswordProtected
          ? { label: t("editor.menu.removePassword"), onClick: docPropsHook.handleRemovePassword, disabled: noDoc }
          : { label: t("editor.menu.addPassword"), onClick: docPropsHook.handleOpenAddPassword, disabled: noDoc },
        { divider: true },
        { label: t("editor.menu.docProperties"), onClick: docPropsHook.handleOpenDocProps, disabled: noDoc },
        { divider: true },
        { label: t("editor.menu.closeDoc"), shortcut: "Alt+Q (Mac: ⌥Q)", onClick: closeDocument, disabled: noDoc },
      ],
    },
    {
      label: t("editor.menu.edit"),
      items: [
        { label: t("editor.menu.undo"), shortcut: "Ctrl+Z", onClick: undo, disabled: noDoc || !canUndo },
        { label: t("editor.menu.redo"), shortcut: "Ctrl+Y", onClick: redo, disabled: noDoc || !canRedo },
        { divider: true },
        { label: t("editor.menu.findInDoc"), shortcut: "Ctrl+F", onClick: openFind, disabled: noDoc },
      ],
    },
    {
      label: t("editor.menu.view"),
      items: [
        {
          label: isSidebarOpen ? t("editor.menu.hideSidebar") : t("editor.menu.showSidebar"),
          onClick: () => setIsSidebarOpen(!isSidebarOpen),
        },
        {
          label: continuousMode ? t("editor.menu.continuousOn") : t("editor.menu.continuousOff"),
          hint: continuousMode ? t("editor.menu.continuousOnHint") : t("editor.menu.continuousOffHint"),
          onClick: toggleContinuousMode,
          disabled: noDoc,
        },
        { divider: true },
        { label: t("editor.menu.zoomIn"), shortcut: "Ctrl++", onClick: zoomIn, disabled: noDoc },
        { label: t("editor.menu.zoomOut"), shortcut: "Ctrl+-", onClick: zoomOut, disabled: noDoc },
        { label: t("editor.menu.actualSize"), shortcut: "Ctrl+0", onClick: () => setZoom(1), disabled: noDoc },
      ],
    },
    {
      label: t("editor.menu.insert"),
      items: [
        { label: t("editor.menu.insertText"), hint: t("editor.menu.insertTextHint"), onClick: toggleTool("insert_text"), disabled: noDoc },
        { label: t("editor.menu.insertImage"), hint: t("editor.menu.insertImageHint"), onClick: insertImage, disabled: noDoc },
        { label: t("editor.menu.insertTable"), hint: t("editor.menu.insertTableHint"), onClick: toggleTool("edit_table"), disabled: noDoc },
        { label: t("editor.menu.stamp"), hint: t("editor.menu.stampHint"), onClick: openStamp, disabled: noDoc },
        { label: t("editor.menu.barcode"), hint: t("editor.menu.barcodeHint"), onClick: openBarcode, disabled: noDoc },
        { label: t("editor.menu.editBarcodeInPage"), hint: t("editor.menu.editBarcodeInPageHint"), onClick: toggleTool("edit_barcode"), disabled: noDoc },
        { label: t("editor.menu.pageNumbers"), hint: t("editor.menu.pageNumbersHint"), onClick: openPageNumbers, disabled: noDoc },
        { label: t("editor.menu.insertPages"), hint: t("editor.menu.insertPagesHint"), onClick: openInsertPages, disabled: noDoc },
      ],
    },
    {
      label: t("editor.menu.annotate"),
      items: [
        { label: t("editor.menu.highlight"), onClick: () => setActiveTool("highlight"), disabled: noDoc },
        { label: t("editor.menu.freetext"), onClick: () => setActiveTool("freetext"), disabled: noDoc },
        { label: t("editor.menu.rect"), onClick: () => setActiveTool("rect"), disabled: noDoc },
        { label: t("editor.menu.textNote"), onClick: () => setActiveTool("text_note"), disabled: noDoc },
        { divider: true },
        { label: t("editor.menu.clearTool"), onClick: () => setActiveTool(null), disabled: !activeTool },
      ],
    },
    {
      label: t("editor.menu.tools"),
      items: [
        { label: t("editor.menu.editText"), hint: t("editor.menu.editTextHint"), onClick: toggleTool("edit_text"), disabled: noDoc },
        { label: t("editor.menu.editImage"), hint: t("editor.menu.editImageHint"), onClick: toggleTool("edit_image"), disabled: noDoc },
        { label: t("editor.menu.editTable"), hint: t("editor.menu.editTableHint"), onClick: toggleTool("edit_table"), disabled: noDoc },
        { label: t("editor.menu.editBarcode"), hint: t("editor.menu.editBarcodeHint"), onClick: toggleTool("edit_barcode"), disabled: noDoc },
        { label: t("editor.menu.cropPage"), hint: t("editor.menu.cropPageHint"), onClick: toggleTool("crop_page"), disabled: noDoc },
        { label: t("editor.menu.fillForm"), hint: t("editor.menu.fillFormHint"), onClick: toggleTool("fill_form"), disabled: noDoc },
        { label: t("editor.menu.redact"), hint: t("editor.menu.redactHint"), onClick: toggleTool("redact"), disabled: noDoc },
        { label: t("editor.menu.inspectFont"), hint: t("editor.menu.inspectFontHint"), onClick: toggleTool("inspect_font"), disabled: noDoc },
        { label: t("editor.menu.redactSearch"), hint: t("editor.menu.redactSearchHint"), onClick: openRedactSearch, disabled: noDoc },
        { label: t("editor.menu.ocrLayer"), hint: t("editor.menu.ocrLayerHint"), onClick: runOcrLayer, disabled: noDoc },
        { label: t("editor.menu.pdpa"), hint: t("editor.menu.pdpaHint"), onClick: openPii, disabled: noDoc },
        { divider: true },
        { label: t("editor.menu.watermark"), hint: t("editor.menu.watermarkHint"), onClick: openWatermark, disabled: noDoc },
        { label: t("editor.menu.compress"), hint: t("editor.menu.compressHint"), onClick: openCompress, disabled: noDoc },
        { label: t("editor.menu.flatten"), hint: t("editor.menu.flattenHint"), onClick: openFlatten, disabled: noDoc },
        { divider: true },
        { label: t("editor.menu.compare"), hint: t("editor.menu.compareHint"), onClick: openCompare, disabled: noDoc },
        { label: t("editor.menu.convertWord"), hint: t("editor.menu.convertWordHint"), onClick: openConvertWord, disabled: noDoc },
      ],
    },
    {
      label: t("editor.menu.signature"),
      items: [
        {
          label: t("editor.menu.electronicSign"),
          hint: t("editor.menu.electronicSignHint"),
          onClick: signatureHook.handleOpenElectronicSign,
          disabled: noDoc || signatureHook.signSubmitting,
        },
        {
          label: t("editor.menu.digitalSign"),
          hint: t("editor.menu.digitalSignHint"),
          onClick: signatureHook.handleOpenDigitalSign,
          disabled: noDoc || signatureHook.signSubmitting,
        },
      ],
    },
    {
      label: t("editor.menu.help"),
      items: [
        { label: t("editor.menu.manual"), onClick: () => window.open("/manual.html", "_blank") },
        { label: t("editor.menu.feedback"), onClick: () => window.open(FEEDBACK_FORM_URL, "_blank", "noopener,noreferrer") },
        { divider: true },
        { label: t("editor.menu.about"), onClick: openAbout },
      ],
    },
  ];
}
