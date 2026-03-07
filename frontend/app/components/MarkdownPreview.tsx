"use client";

import { useMemo } from "react";

/**
 * Lightweight markdown-to-HTML renderer with zero external dependencies.
 * Handles: headings, bold, italic, inline code, code blocks, links,
 *          unordered/ordered lists, blockquotes, horizontal rules, tables.
 */

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function renderInline(text: string): string {
  let result = escapeHtml(text);

  // Inline code (must come before bold/italic to avoid conflicts)
  result = result.replace(/`([^`]+)`/g, '<code class="md-inline-code">$1</code>');

  // Bold + italic
  result = result.replace(/\*\*\*(.+?)\*\*\*/g, "<strong><em>$1</em></strong>");
  // Bold
  result = result.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  // Italic
  result = result.replace(/\*(.+?)\*/g, "<em>$1</em>");
  // Links
  result = result.replace(
    /\[([^\]]+)\]\(([^)]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener noreferrer" class="md-link">$1</a>'
  );

  return result;
}

function parseMarkdown(source: string): string {
  const lines = source.split("\n");
  const html: string[] = [];
  let i = 0;

  const flushParagraph = (buffer: string[]) => {
    if (buffer.length > 0) {
      html.push(`<p>${buffer.map(renderInline).join("<br/>")}</p>`);
      buffer.length = 0;
    }
  };

  const paragraphBuffer: string[] = [];

  while (i < lines.length) {
    const line = lines[i];

    // Fenced code block
    if (line.trimStart().startsWith("```")) {
      flushParagraph(paragraphBuffer);
      const lang = line.trimStart().slice(3).trim();
      const codeLines: string[] = [];
      i++;
      while (i < lines.length && !lines[i].trimStart().startsWith("```")) {
        codeLines.push(lines[i]);
        i++;
      }
      i++; // skip closing ```
      const langAttr = lang ? ` data-lang="${escapeHtml(lang)}"` : "";
      html.push(
        `<div class="md-code-block"><div class="md-code-header">${escapeHtml(lang || "code")}</div><pre${langAttr}><code>${escapeHtml(codeLines.join("\n"))}</code></pre></div>`
      );
      continue;
    }

    // Horizontal rule
    if (/^(\s*[-*_]\s*){3,}$/.test(line)) {
      flushParagraph(paragraphBuffer);
      html.push('<hr class="md-hr"/>');
      i++;
      continue;
    }

    // Headings
    const headingMatch = line.match(/^(#{1,6})\s+(.+)/);
    if (headingMatch) {
      flushParagraph(paragraphBuffer);
      const level = headingMatch[1].length;
      html.push(`<h${level} class="md-h${level}">${renderInline(headingMatch[2])}</h${level}>`);
      i++;
      continue;
    }

    // Blockquote
    if (line.startsWith("> ") || line === ">") {
      flushParagraph(paragraphBuffer);
      const quoteLines: string[] = [];
      while (i < lines.length && (lines[i].startsWith("> ") || lines[i] === ">")) {
        quoteLines.push(lines[i].replace(/^>\s?/, ""));
        i++;
      }
      html.push(`<blockquote class="md-blockquote">${quoteLines.map(renderInline).join("<br/>")}</blockquote>`);
      continue;
    }

    // Table (detect header row with | separators)
    if (line.includes("|") && i + 1 < lines.length && /^\|?\s*[-:]+[-|\s:]*$/.test(lines[i + 1])) {
      flushParagraph(paragraphBuffer);
      const parseRow = (row: string) =>
        row.split("|").map(c => c.trim()).filter(c => c.length > 0);

      const headers = parseRow(line);
      i += 2; // skip header + separator
      const rows: string[][] = [];
      while (i < lines.length && lines[i].includes("|") && lines[i].trim() !== "") {
        rows.push(parseRow(lines[i]));
        i++;
      }

      html.push('<div class="md-table-wrap"><table class="md-table">');
      html.push("<thead><tr>");
      headers.forEach(h => html.push(`<th>${renderInline(h)}</th>`));
      html.push("</tr></thead><tbody>");
      rows.forEach(row => {
        html.push("<tr>");
        row.forEach(c => html.push(`<td>${renderInline(c)}</td>`));
        html.push("</tr>");
      });
      html.push("</tbody></table></div>");
      continue;
    }

    // Unordered list
    if (/^\s*[-*+]\s+/.test(line)) {
      flushParagraph(paragraphBuffer);
      html.push('<ul class="md-ul">');
      while (i < lines.length && /^\s*[-*+]\s+/.test(lines[i])) {
        const content = lines[i].replace(/^\s*[-*+]\s+/, "");
        html.push(`<li>${renderInline(content)}</li>`);
        i++;
      }
      html.push("</ul>");
      continue;
    }

    // Ordered list
    if (/^\s*\d+[.)]\s+/.test(line)) {
      flushParagraph(paragraphBuffer);
      html.push('<ol class="md-ol">');
      while (i < lines.length && /^\s*\d+[.)]\s+/.test(lines[i])) {
        const content = lines[i].replace(/^\s*\d+[.)]\s+/, "");
        html.push(`<li>${renderInline(content)}</li>`);
        i++;
      }
      html.push("</ol>");
      continue;
    }

    // Empty line → flush paragraph
    if (line.trim() === "") {
      flushParagraph(paragraphBuffer);
      i++;
      continue;
    }

    // Regular text → accumulate into paragraph
    paragraphBuffer.push(line);
    i++;
  }

  flushParagraph(paragraphBuffer);
  return html.join("\n");
}

interface MarkdownPreviewProps {
  children: string;
  className?: string;
}

export default function MarkdownPreview({ children, className = "" }: MarkdownPreviewProps) {
  const html = useMemo(() => parseMarkdown(children), [children]);

  return (
    <div
      className={`md-preview ${className}`}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
