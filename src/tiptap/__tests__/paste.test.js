import { describe, it, expect, vi } from "vitest";
import { smartPasteHandler, looksLikeMarkdown } from "../paste.js";

function pasteEvent({ html, text, files } = {}) {
  const types = [];
  if (html) types.push("text/html");
  if (text) types.push("text/plain");
  return {
    clipboardData: {
      types,
      files: files || [],
      getData: (t) => (t === "text/html" ? html ?? "" : t === "text/plain" ? text ?? "" : ""),
    },
    preventDefault: vi.fn(),
  };
}

function fakeView({ inCodeBlock = false } = {}) {
  return {
    state: {
      selection: {
        $from: {
          parent: { type: { name: inCodeBlock ? "codeBlock" : "paragraph" } },
        },
      },
    },
    inserted: [],
    pasteHTML(html) { this.inserted.push(html); },
  };
}

describe("looksLikeMarkdown", () => {
  it("detects ATX headings", () => {
    expect(looksLikeMarkdown("## Hello")).toBe(true);
  });
  it("detects fenced code blocks", () => {
    expect(looksLikeMarkdown("```\ncode\n```")).toBe(true);
  });
  it("detects bullet lists", () => {
    expect(looksLikeMarkdown("- item one\n- item two")).toBe(true);
  });
  it("detects markdown links", () => {
    expect(looksLikeMarkdown("see [docs](https://x.com)")).toBe(true);
  });
  it("returns false for plain prose", () => {
    expect(looksLikeMarkdown("Just a sentence with no markup.")).toBe(false);
  });
});

describe("smartPasteHandler", () => {
  it("returns false (default paste) inside a code block, even for markdown", () => {
    const view = fakeView({ inCodeBlock: true });
    const ev = pasteEvent({ text: "## not a heading" });
    expect(smartPasteHandler(view, ev)).toBe(false);
    expect(view.inserted).toEqual([]);
  });

  it("normalises and inserts Office HTML when present", () => {
    const view = fakeView();
    const officeHtml = '<p class="MsoNormal" style="font-family:Calibri"><b>Hi</b></p>';
    const ev = pasteEvent({ html: officeHtml });
    expect(smartPasteHandler(view, ev)).toBe(true);
    expect(view.inserted[0]).toContain("<strong>");
    expect(view.inserted[0]).not.toMatch(/style=|class=/);
  });

  it("converts markdown text to HTML and inserts", () => {
    const view = fakeView();
    const ev = pasteEvent({ text: "## Hello\n\n**world**" });
    expect(smartPasteHandler(view, ev)).toBe(true);
    expect(view.inserted[0]).toContain("<h2>");
    expect(view.inserted[0]).toContain("<strong>world</strong>");
  });

  it("drops image-only clipboard (no upload in v1)", () => {
    const view = fakeView();
    const ev = pasteEvent({ files: [new File([""], "x.png", { type: "image/png" })] });
    expect(smartPasteHandler(view, ev)).toBe(true);
    expect(view.inserted).toEqual([]);
    expect(ev.preventDefault).toHaveBeenCalled();
  });

  it("returns false for plain prose without markdown signals", () => {
    const view = fakeView();
    const ev = pasteEvent({ text: "Just a sentence." });
    expect(smartPasteHandler(view, ev)).toBe(false);
    expect(view.inserted).toEqual([]);
  });
});
