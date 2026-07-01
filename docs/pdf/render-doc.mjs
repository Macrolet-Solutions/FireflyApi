import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import { marked } from "marked";
import { chromium } from "playwright";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const docsRoot = path.resolve(__dirname, "..");
const templatePath = path.join(__dirname, "template.html");
const cssPath = path.join(__dirname, "print.css");
const logoPath = path.join(__dirname, "assets", "logo-firefly-web.webp");
const outDir = path.join(__dirname, "out");

marked.setOptions({
  gfm: true,
  breaks: false,
});

export async function renderDocument(config) {
  const markdownPath = path.join(docsRoot, config.source);
  const htmlOutPath = path.join(outDir, `${config.outputBase}.html`);
  const preferredPdfOutPath = path.join(outDir, `${config.outputBase}.pdf`);
  let pdfOutPath = preferredPdfOutPath;

  const markdown = await fs.readFile(markdownPath, "utf8");
  const template = await fs.readFile(templatePath, "utf8");
  const logoSrc = createLogoPanelDataUri(await toDataUri(logoPath, "image/webp"));
  const metadata = readMetadata(markdown);
  const { markdown: anchoredMarkdown, toc } = addHeadingAnchors(markdown);
  const contentHtml = marked.parse(anchoredMarkdown);
  const tocHtml = renderToc(toc);

  await fs.mkdir(outDir, { recursive: true });

  const contextValue = config.contextValue ?? metadata[config.contextMetadataKey] ?? "";
  const html = template
    .replaceAll("{{TITLE}}", escapeHtml(config.title))
    .replaceAll("{{DOCS_BASE_URI}}", pathToFileURL(`${docsRoot}${path.sep}`).href)
    .replaceAll("{{CSS_PATH}}", pathToFileURL(cssPath).href)
    .replaceAll("{{LOGO_SRC}}", logoSrc)
    .replaceAll("{{COVER_LABEL}}", escapeHtml(config.coverLabel))
    .replaceAll("{{COVER_TITLE}}", config.coverTitle)
    .replaceAll("{{COVER_SUBTITLE}}", escapeHtml(config.coverSubtitle))
    .replaceAll("{{DOC_VERSION}}", escapeHtml(metadata["Document version"] ?? "0.1"))
    .replaceAll("{{DOC_DATE}}", escapeHtml(metadata["Document date"] ?? "2026-07-01"))
    .replaceAll("{{CONTEXT_LABEL}}", escapeHtml(config.contextLabel))
    .replaceAll("{{CONTEXT_VALUE}}", escapeHtml(contextValue))
    .replaceAll("{{TOC}}", tocHtml)
    .replaceAll("{{CONTENT}}", contentHtml);

  await fs.writeFile(htmlOutPath, html, "utf8");

  const browser = await chromium.launch();
  try {
    const page = await browser.newPage({ viewport: { width: 1240, height: 1754 } });
    await page.goto(pathToFileURL(htmlOutPath).href, { waitUntil: "networkidle" });
    try {
      await renderPdf(page, pdfOutPath, logoSrc, metadata, config);
    } catch (error) {
      if (error?.code !== "EBUSY") throw error;
      pdfOutPath = path.join(
        outDir,
        `${config.outputBase}-${new Date().toISOString().replace(/[:.]/g, "-")}.pdf`,
      );
      console.warn(
        `Preferred PDF is locked; writing alternate file ${path.basename(pdfOutPath)}.`,
      );
      await renderPdf(page, pdfOutPath, logoSrc, metadata, config);
    }
  } finally {
    await browser.close();
  }

  console.log(`HTML written to ${path.relative(process.cwd(), htmlOutPath)}`);
  console.log(`PDF written to ${path.relative(process.cwd(), pdfOutPath)}`);
}

function readMetadata(source) {
  const metadata = {};
  const lines = source.split(/\r?\n/);
  const startIndex = lines.findIndex((line) => line.trim() === "| Item | Value |");
  if (startIndex === -1) return metadata;

  for (const line of lines.slice(startIndex + 2)) {
    if (!line.trim().startsWith("|")) break;
    const cells = line
      .trim()
      .slice(1, -1)
      .split("|")
      .map((cell) => cell.trim().replace(/^`|`$/g, ""));
    if (cells.length >= 2) metadata[cells[0]] = cells[1];
  }
  return metadata;
}

function addHeadingAnchors(source) {
  const toc = [];
  const usedSlugs = new Map();
  let inFence = false;

  const lines = source.split(/\r?\n/).map((line) => {
    if (/^\s*```/.test(line)) {
      inFence = !inFence;
      return line;
    }
    if (inFence) return line;

    const match = /^(#{1,4})\s+(.+?)\s*$/.exec(line);
    if (!match) return line;

    const depth = match[1].length;
    const text = match[2].replace(/\s+#+$/, "").trim();
    const slug = uniqueSlug(slugify(text), usedSlugs);
    if (depth === 2 || depth === 3) {
      toc.push({ depth, text, slug });
    }
    return `<h${depth} id="${escapeAttribute(slug)}">${escapeHtml(text)}</h${depth}>`;
  });

  return { markdown: lines.join("\n"), toc };
}

function renderToc(toc) {
  const relevant = toc.filter(
    (item) =>
      item.text !== "Document And API Version" &&
      item.text !== "Document And Guide Version",
  );
  return `<ol class="toc">${relevant
    .map(
      (item) =>
        `<li class="toc-level-${item.depth}"><a href="#${escapeAttribute(item.slug)}">${escapeHtml(item.text)}</a></li>`,
    )
    .join("\n")}</ol>`;
}

function renderHeaderTemplate(logoSrc, config) {
  return `
    <div style="width:100%;padding:0 10mm;font-family:Segoe UI,Arial,sans-serif;font-size:8px;color:#667085;">
      <div style="display:flex;align-items:center;justify-content:space-between;width:100%;padding-bottom:6px;border-bottom:1px solid #eaecf0;">
        <img src="${logoSrc}" style="width:92px;height:auto;" />
        <span>${escapeHtml(config.headerTitle)}</span>
      </div>
    </div>`;
}

async function renderPdf(page, outputPath, logoSrc, metadata, config) {
  await page.pdf({
    path: outputPath,
    format: "A4",
    printBackground: true,
    preferCSSPageSize: true,
    displayHeaderFooter: true,
    headerTemplate: renderHeaderTemplate(logoSrc, config),
    footerTemplate: renderFooterTemplate(metadata["Document version"] ?? "0.1"),
  });
}

function renderFooterTemplate(version) {
  return `
    <div style="width:100%;padding:0 10mm;font-family:Segoe UI,Arial,sans-serif;font-size:8px;color:#667085;">
      <div style="display:flex;align-items:center;justify-content:space-between;width:100%;padding-top:6px;border-top:1px solid #eaecf0;">
        <span>Macrolet Firefly API Service · v${escapeHtml(version)}</span>
        <span>Page <span class="pageNumber"></span> of <span class="totalPages"></span></span>
      </div>
    </div>`;
}

async function toDataUri(filePath, mimeType) {
  const data = await fs.readFile(filePath);
  return `data:${mimeType};base64,${data.toString("base64")}`;
}

function createLogoPanelDataUri(logoDataUri) {
  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" width="1256" height="506" viewBox="0 0 1256 506">
      <rect width="1256" height="506" rx="56" fill="#111827"/>
      <image href="${logoDataUri}" x="80" y="55" width="1096" height="396" preserveAspectRatio="xMidYMid meet"/>
    </svg>`;
  return `data:image/svg+xml;base64,${Buffer.from(svg).toString("base64")}`;
}

function slugify(text) {
  return text
    .toLowerCase()
    .replace(/`([^`]+)`/g, "$1")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "") || "section";
}

function uniqueSlug(base, usedSlugs) {
  const count = usedSlugs.get(base) ?? 0;
  usedSlugs.set(base, count + 1);
  return count === 0 ? base : `${base}-${count + 1}`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function escapeAttribute(value) {
  return escapeHtml(value).replaceAll("'", "&#39;");
}
