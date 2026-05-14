import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { normaliseOfficeHtml, looksLikeOfficeHtml } from "../paste.js";

const here = dirname(fileURLToPath(import.meta.url));
const fixture = (name) => readFileSync(resolve(here, "fixtures", name), "utf8");

describe("looksLikeOfficeHtml", () => {
  it("detects Google Docs paste via docs-internal-guid", () => {
    expect(looksLikeOfficeHtml(fixture("google-docs-paste.html"))).toBe(true);
  });
  it("detects Word paste via mso- and office namespaces", () => {
    expect(looksLikeOfficeHtml(fixture("word-paste.html"))).toBe(true);
  });
  it("detects Notion paste via data-pm-slice", () => {
    expect(looksLikeOfficeHtml(fixture("notion-paste.html"))).toBe(true);
  });
  it("returns false for plain HTML", () => {
    expect(looksLikeOfficeHtml("<p>hello</p>")).toBe(false);
  });
});

describe("normaliseOfficeHtml", () => {
  it("strips style and class attributes", () => {
    const out = normaliseOfficeHtml(fixture("google-docs-paste.html"));
    expect(out).not.toMatch(/style=/);
    expect(out).not.toMatch(/class=/);
  });
  it("promotes <b> with font-weight:bold context to <strong>", () => {
    const out = normaliseOfficeHtml(fixture("google-docs-paste.html"));
    expect(out).toContain("<strong>");
    expect(out).toContain("Headline");
  });
  it("preserves <a href> targets", () => {
    const out = normaliseOfficeHtml(fixture("google-docs-paste.html"));
    expect(out).toContain('href="https://example.com"');
  });
  it("removes Office namespaced tags from Word paste", () => {
    const out = normaliseOfficeHtml(fixture("word-paste.html"));
    expect(out).not.toMatch(/<o:/);
    expect(out).not.toMatch(/<w:/);
    expect(out).not.toMatch(/MsoNormal/);
  });
  it("removes <style>, <meta>, <link>, <script>", () => {
    const out = normaliseOfficeHtml(fixture("word-paste.html"));
    expect(out).not.toMatch(/<style/);
    expect(out).not.toMatch(/<meta/);
    expect(out).not.toMatch(/<script/);
  });
  it("preserves Notion's already-semantic markup", () => {
    const out = normaliseOfficeHtml(fixture("notion-paste.html"));
    expect(out).toContain("<h2>Heading</h2>");
    expect(out).toContain("<strong>bold</strong>");
  });
});
