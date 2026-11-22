import { describe, expect, it } from "vitest";
import { applyDraftChange, collectDirtyUpdates, initDraftValues } from "../utils/formFillUtils.js";

const FIELDS = [
  { xref: 10, page: 0, name: "fullname", type: "text", value: "", read_only: false },
  { xref: 11, page: 0, name: "agree", type: "checkbox", value: false, read_only: false },
  { xref: 12, page: 0, name: "gender", type: "radio", value: true, read_only: false },
  { xref: 13, page: 0, name: "gender", type: "radio", value: false, read_only: false },
  { xref: 14, page: 0, name: "code", type: "text", value: "DOC-1", read_only: true },
];

describe("formFillUtils", () => {
  it("initializes draft values map by xref", () => {
    expect(initDraftValues(FIELDS)).toEqual({
      10: "",
      11: false,
      12: true,
      13: false,
      14: "DOC-1",
    });
  });

  it("unchecks sibling radio buttons when another radio in the same group is selected", () => {
    const start = initDraftValues(FIELDS);
    const updated = applyDraftChange(start, FIELDS, FIELDS[3], true);
    expect(updated[13]).toBe(true);
    expect(updated[12]).toBe(false);
  });

  it("collects only dirty and non-readonly updates", () => {
    let draft = initDraftValues(FIELDS);
    draft = applyDraftChange(draft, FIELDS, FIELDS[0], "สมชาย");
    draft = applyDraftChange(draft, FIELDS, FIELDS[1], true);
    draft[14] = "MODIFIED_READONLY";

    expect(collectDirtyUpdates(FIELDS, draft)).toEqual([
      { xref: 10, page: 0, value: "สมชาย" },
      { xref: 11, page: 0, value: true },
    ]);
  });
});
