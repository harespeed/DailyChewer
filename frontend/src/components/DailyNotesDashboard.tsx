import { Button, Empty, Input, Modal, Popover, Radio, Select, Space, Spin, Tag, Typography, message } from "antd";
import { DownloadOutlined, FileTextOutlined, SaveOutlined } from "@ant-design/icons";
import { useEffect, useMemo, useState } from "react";
import {
  DailyNote,
  DailyNoteDay,
  NoteWeeklyRangeResult,
  NoteWeeklyRangeTaskResponse,
  createWeeklyRangeTaskFromNotes,
  createDailyNote,
  deleteDailyNote,
  fetchDailyNotes,
  fetchWeeklyRangeTaskFromNotes,
  generateDailyFromNotes,
  generateWeeklyFromNotes,
  updateDailyNote,
} from "../api/client";
import { FloatingErrorButton, createFloatingErrorEntry, type FloatingErrorEntry } from "./FloatingErrorButton";

const weekdayLabels = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const periodLabels: Record<string, string> = {
  morning: "上午",
  afternoon: "下午",
};
const exportFormatOptions = [
  { label: "Markdown", value: "markdown" },
  { label: "TXT", value: "txt" },
  { label: "XLSX", value: "xlsx" },
] as const;

type ExportFormat = (typeof exportFormatOptions)[number]["value"];
type CsvDayColumn = { date: string; label: string };
type ParsedReportDay = {
  work: string[];
  growth: string[];
  morning: string[];
  afternoon: string[];
  problems: string[];
  solutions: string[];
  problemSolutionPairs: string[];
};

const weekdayLabelMap: Record<string, string> = {
  Monday: "周一",
  Tuesday: "周二",
  Wednesday: "周三",
  Thursday: "周四",
  Friday: "周五",
  Saturday: "周六",
  Sunday: "周日",
  Mon: "周一",
  Tue: "周二",
  Wed: "周三",
  Thu: "周四",
  Fri: "周五",
  Sat: "周六",
  Sun: "周日",
};

function toDateKey(date: Date) {
  return [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, "0"),
    String(date.getDate()).padStart(2, "0"),
  ].join("-");
}

function monthKey(date: Date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`;
}

function buildMonthCells(viewDate: Date) {
  const first = new Date(viewDate.getFullYear(), viewDate.getMonth(), 1);
  const start = new Date(first);
  start.setDate(first.getDate() - first.getDay());
  return Array.from({ length: 42 }, (_, index) => {
    const cell = new Date(start);
    cell.setDate(start.getDate() + index);
    return cell;
  });
}

function currentPeriod() {
  return new Date().getHours() < 12 ? "morning" : "afternoon";
}

function normalizeRange(left: string, right: string) {
  return left <= right ? { from: left, to: right } : { from: right, to: left };
}

function isDateInRange(date: string, from: string, to: string) {
  return date >= from && date <= to;
}

function notePreview(day?: DailyNoteDay) {
  if (!day) {
    return <Typography.Text type="secondary">No note yet.</Typography.Text>;
  }
  return (
    <div className="note-popover">
      <Typography.Text strong>{day.date}</Typography.Text>
      {day.notes.map((note) => (
        <div className="note-popover-item" key={note.id}>
          <Tag color="green">{periodLabels[note.period] || note.period}</Tag>
          <Typography.Paragraph ellipsis={{ rows: 4 }}>{note.content}</Typography.Paragraph>
        </div>
      ))}
    </div>
  );
}

function getNotesErrorMessage(error: any, fallback: string) {
  const detail = error?.response?.data?.detail;
  if (detail === "Not Found" || error?.response?.status === 404) {
    return "Calendar 便条接口返回 Not Found。请确认后端已重启到最新代码，并已执行数据库迁移 `alembic upgrade head`。";
  }
  if (typeof detail === "string") {
    return detail;
  }
  return error?.message || fallback;
}

function wait(milliseconds: number) {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

function stripMarkdown(markdown: string) {
  return markdown
    .replace(/^#{1,6}\s+/gm, "")
    .replace(/^\s*[-*+]\s+/gm, "")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/`([^`]+)`/g, "$1")
    .trim();
}

function buildExportContent(markdown: string, format: ExportFormat, csvColumns: CsvDayColumn[] = []) {
  if (format === "markdown") {
    return markdown;
  }
  if (format === "txt") {
    return stripMarkdown(markdown);
  }
  return buildStageReportXlsx(markdown, csvColumns);
}

function exportExtension(format: ExportFormat) {
  if (format === "xlsx") {
    return "xlsx";
  }
  return format === "markdown" ? "md" : format;
}

function exportMimeType(format: ExportFormat) {
  if (format === "xlsx") {
    return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
  }
  if (format === "markdown") {
    return "text/markdown;charset=utf-8";
  }
  return "text/plain;charset=utf-8";
}

function exportAcceptType(format: ExportFormat) {
  const extension = `.${exportExtension(format)}`;
  return { [exportMimeType(format).split(";")[0]]: [extension] };
}

async function saveReportToFile(content: string | Blob, format: ExportFormat, suggestedName: string) {
  const fileName = `${suggestedName}.${exportExtension(format)}`;
  const blob = content instanceof Blob ? content : new Blob([content], { type: exportMimeType(format) });
  const picker = (window as any).showSaveFilePicker;
  if (typeof picker === "function") {
    const handle = await picker({
      suggestedName: fileName,
      types: [{ description: format.toUpperCase(), accept: exportAcceptType(format) }],
    });
    const writable = await handle.createWritable();
    await writable.write(blob);
    await writable.close();
    return;
  }

  const blobUrl = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = blobUrl;
  link.download = fileName;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(blobUrl);
}

function normalizeWeekdayLabel(weekday: string, date: string) {
  if (weekdayLabelMap[weekday]) {
    return weekdayLabelMap[weekday];
  }
  const parsed = new Date(`${date}T00:00:00`);
  return weekdayLabels[parsed.getDay()] || weekday;
}

function collectCsvColumns(days: DailyNoteDay[], from: string, to: string) {
  return days
    .filter((day) => isDateInRange(day.date, from, to))
    .sort((left, right) => left.date.localeCompare(right.date))
    .map((day) => ({
      date: day.date,
      label: `${normalizeWeekdayLabel(day.weekday, day.date)} ${day.date}`,
    }));
}

function buildStageReportRows(markdown: string, columns: CsvDayColumn[]) {
  const parsed = parseWeeklyMarkdown(markdown);
  const resolvedColumns =
    columns.length > 0
      ? columns
      : Object.keys(parsed)
          .sort()
          .map((date) => ({ date, label: date }));
  const rowDefinitions: Array<[string, keyof ParsedReportDay]> = [
    ["上午", "morning"],
    ["下午", "afternoon"],
    ["遇到的问题+解决方案", "problemSolutionPairs"],
  ];
  const summary = buildWeeklySummary(markdown, parsed);
  return [
    ["时间段", ...resolvedColumns.map((column) => column.label)],
    ...rowDefinitions.map(([label, key]) => [
      label,
      ...resolvedColumns.map((column) => joinReportItems(parsed[column.date]?.[key] || [], key === "problemSolutionPairs" ? "\n" : "; ")),
    ]),
    ["本周总结", summary, ...resolvedColumns.slice(1).map(() => "")],
  ];
}

function buildStageReportXlsx(markdown: string, columns: CsvDayColumn[]) {
  const rows = buildStageReportRows(markdown, columns);
  const worksheet = buildWorksheetXml(rows);
  const now = new Date().toISOString();
  return buildZipBlob({
    "[Content_Types].xml": `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>`,
    "_rels/.rels": `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>`,
    "docProps/app.xml": `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"><Application>DailyChewer</Application></Properties>`,
    "docProps/core.xml": `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><dc:creator>DailyChewer</dc:creator><dcterms:created xsi:type="dcterms:W3CDTF">${now}</dcterms:created><dcterms:modified xsi:type="dcterms:W3CDTF">${now}</dcterms:modified></cp:coreProperties>`,
    "xl/workbook.xml": `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="阶段报" sheetId="1" r:id="rId1"/></sheets></workbook>`,
    "xl/_rels/workbook.xml.rels": `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>`,
    "xl/styles.xml": buildWorkbookStylesXml(),
    "xl/worksheets/sheet1.xml": worksheet,
  });
}

function buildWorksheetXml(rows: string[][]) {
  const columns = rows[0]?.length || 1;
  const summaryRowNumber = rows.length;
  const summaryMerge = columns > 2 ? `<mergeCells count="1"><mergeCell ref="B${summaryRowNumber}:${columnName(columns - 1)}${summaryRowNumber}"/></mergeCells>` : "";
  const columnXml = Array.from({ length: columns }, (_, index) => {
    const width = index === 0 ? 20 : 32;
    return `<col min="${index + 1}" max="${index + 1}" width="${width}" customWidth="1"/>`;
  }).join("");
  const rowXml = rows
    .map((row, rowIndex) => {
      const cells = row
        .map((value, columnIndex) => {
          const isSummaryRow = rowIndex === rows.length - 1;
          const style = rowIndex === 0 ? 1 : columnIndex === 0 ? 2 : isSummaryRow ? 4 : 3;
          return buildInlineStringCell(columnIndex, rowIndex, value, style);
        })
        .join("");
      const height = rowIndex === 0 ? 24 : rowIndex === rows.length - 1 ? 96 : 72;
      return `<row r="${rowIndex + 1}" ht="${height}" customHeight="1">${cells}</row>`;
    })
    .join("");
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <cols>${columnXml}</cols>
  <sheetData>${rowXml}</sheetData>
  ${summaryMerge}
</worksheet>`;
}

function buildInlineStringCell(columnIndex: number, rowIndex: number, value: string, style: number) {
  const reference = `${columnName(columnIndex)}${rowIndex + 1}`;
  return `<c r="${reference}" t="inlineStr" s="${style}"><is><t xml:space="preserve">${escapeXml(value)}</t></is></c>`;
}

function columnName(index: number) {
  let current = index + 1;
  let name = "";
  while (current > 0) {
    const remainder = (current - 1) % 26;
    name = String.fromCharCode(65 + remainder) + name;
    current = Math.floor((current - 1) / 26);
  }
  return name;
}

function escapeXml(value: string) {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

function buildWorkbookStylesXml() {
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="2">
    <font><sz val="11"/><name val="Arial"/></font>
    <font><b/><sz val="11"/><name val="Arial"/></font>
  </fonts>
  <fills count="4">
    <fill><patternFill patternType="none"/></fill>
    <fill><patternFill patternType="gray125"/></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFD9EAF7"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFFFF2CC"/><bgColor indexed="64"/></patternFill></fill>
  </fills>
  <borders count="2">
    <border><left/><right/><top/><bottom/><diagonal/></border>
    <border>
      <left style="thin"><color rgb="FF7F8EA3"/></left>
      <right style="thin"><color rgb="FF7F8EA3"/></right>
      <top style="thin"><color rgb="FF7F8EA3"/></top>
      <bottom style="thin"><color rgb="FF7F8EA3"/></bottom>
      <diagonal/>
    </border>
  </borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="5">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
    <xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>
    <xf numFmtId="0" fontId="1" fillId="3" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>
    <xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>
    <xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1" applyAlignment="1"><alignment horizontal="left" vertical="top" wrapText="1"/></xf>
  </cellXfs>
  <cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>`;
}

function buildZipBlob(files: Record<string, string>) {
  const encoder = new TextEncoder();
  const localParts: Uint8Array[] = [];
  const centralParts: Uint8Array[] = [];
  let offset = 0;
  Object.entries(files).forEach(([name, content]) => {
    const nameBytes = encoder.encode(name);
    const data = encoder.encode(content);
    const crc = crc32(data);
    const localHeader = createZipLocalHeader(nameBytes, data, crc);
    localParts.push(localHeader, data);
    centralParts.push(createZipCentralHeader(nameBytes, data, crc, offset));
    offset += localHeader.length + data.length;
  });
  const centralSize = centralParts.reduce((sum, part) => sum + part.length, 0);
  const end = createZipEndRecord(centralParts.length, centralSize, offset);
  return new Blob([...localParts, ...centralParts, end].map(toArrayBuffer), { type: exportMimeType("xlsx") });
}

function toArrayBuffer(bytes: Uint8Array) {
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer;
}

function createZipLocalHeader(nameBytes: Uint8Array, data: Uint8Array, crc: number) {
  const header = new Uint8Array(30 + nameBytes.length);
  const view = new DataView(header.buffer);
  view.setUint32(0, 0x04034b50, true);
  view.setUint16(4, 20, true);
  view.setUint16(6, 0, true);
  view.setUint16(8, 0, true);
  view.setUint16(10, zipTime(), true);
  view.setUint16(12, zipDate(), true);
  view.setUint32(14, crc, true);
  view.setUint32(18, data.length, true);
  view.setUint32(22, data.length, true);
  view.setUint16(26, nameBytes.length, true);
  view.setUint16(28, 0, true);
  header.set(nameBytes, 30);
  return header;
}

function createZipCentralHeader(nameBytes: Uint8Array, data: Uint8Array, crc: number, offset: number) {
  const header = new Uint8Array(46 + nameBytes.length);
  const view = new DataView(header.buffer);
  view.setUint32(0, 0x02014b50, true);
  view.setUint16(4, 20, true);
  view.setUint16(6, 20, true);
  view.setUint16(8, 0, true);
  view.setUint16(10, 0, true);
  view.setUint16(12, zipTime(), true);
  view.setUint16(14, zipDate(), true);
  view.setUint32(16, crc, true);
  view.setUint32(20, data.length, true);
  view.setUint32(24, data.length, true);
  view.setUint16(28, nameBytes.length, true);
  view.setUint16(30, 0, true);
  view.setUint16(32, 0, true);
  view.setUint16(34, 0, true);
  view.setUint16(36, 0, true);
  view.setUint32(38, 0, true);
  view.setUint32(42, offset, true);
  header.set(nameBytes, 46);
  return header;
}

function createZipEndRecord(fileCount: number, centralSize: number, centralOffset: number) {
  const record = new Uint8Array(22);
  const view = new DataView(record.buffer);
  view.setUint32(0, 0x06054b50, true);
  view.setUint16(4, 0, true);
  view.setUint16(6, 0, true);
  view.setUint16(8, fileCount, true);
  view.setUint16(10, fileCount, true);
  view.setUint32(12, centralSize, true);
  view.setUint32(16, centralOffset, true);
  view.setUint16(20, 0, true);
  return record;
}

function zipTime() {
  const date = new Date();
  return (date.getHours() << 11) | (date.getMinutes() << 5) | Math.floor(date.getSeconds() / 2);
}

function zipDate() {
  const date = new Date();
  return ((date.getFullYear() - 1980) << 9) | ((date.getMonth() + 1) << 5) | date.getDate();
}

function crc32(data: Uint8Array) {
  let crc = 0xffffffff;
  for (const byte of data) {
    crc = (crc >>> 8) ^ crcTable[(crc ^ byte) & 0xff];
  }
  return (crc ^ 0xffffffff) >>> 0;
}

const crcTable = Array.from({ length: 256 }, (_, index) => {
  let value = index;
  for (let bit = 0; bit < 8; bit += 1) {
    value = value & 1 ? 0xedb88320 ^ (value >>> 1) : value >>> 1;
  }
  return value >>> 0;
});

function parseWeeklyMarkdown(markdown: string) {
  const dayPattern = /^##\s+(.+?)\s+(\d{4}-\d{2}-\d{2})\s*$/gm;
  const matches = Array.from(markdown.matchAll(dayPattern));
  const result: Record<string, ParsedReportDay> = {};
  matches.forEach((match, index) => {
    const date = match[2];
    const start = (match.index || 0) + match[0].length;
    const end = index + 1 < matches.length ? matches[index + 1].index || markdown.length : markdown.length;
    result[date] = parseDayMarkdown(markdown.slice(start, end));
  });
  return result;
}

function parseDayMarkdown(dayMarkdown: string): ParsedReportDay {
  const morning = extractPeriodMarkdown(dayMarkdown, "上午");
  const afternoon = extractPeriodMarkdown(dayMarkdown, "下午");
  const morningWork = extractSubsectionItems(morning, "工作内容");
  const afternoonWork = extractSubsectionItems(afternoon, "工作内容");
  const morningGrowth = extractSubsectionItems(morning, "个人成长");
  const afternoonGrowth = extractSubsectionItems(afternoon, "个人成长");
  const morningProblems = extractSubsectionItems(morning, "问题总结");
  const morningSolutions = extractSubsectionItems(morning, "解决方案");
  const afternoonProblems = extractSubsectionItems(afternoon, "问题总结");
  const afternoonSolutions = extractSubsectionItems(afternoon, "解决方案");
  const problems = [...morningProblems, ...afternoonProblems];
  const solutions = [...morningSolutions, ...afternoonSolutions];
  return {
    work: [...morningWork, ...afternoonWork],
    growth: [...morningGrowth, ...afternoonGrowth],
    morning: [...morningWork, ...morningGrowth],
    afternoon: [...afternoonWork, ...afternoonGrowth],
    problems,
    solutions,
    problemSolutionPairs: [
      ...pairProblemsAndSolutions(morningProblems, morningSolutions),
      ...pairProblemsAndSolutions(afternoonProblems, afternoonSolutions),
    ].map((item, index) => item.replace(/^\d+\.\s*/, `${index + 1}. `)),
  };
}

function extractPeriodMarkdown(dayMarkdown: string, period: "上午" | "下午") {
  const pattern = new RegExp(`^###\\s+${period}\\s*$`, "m");
  const match = dayMarkdown.match(pattern);
  if (!match || match.index === undefined) {
    return "";
  }
  const start = match.index + match[0].length;
  const nextHeading = dayMarkdown.slice(start).search(/^###\s+/m);
  return nextHeading >= 0 ? dayMarkdown.slice(start, start + nextHeading) : dayMarkdown.slice(start);
}

function extractSubsectionItems(periodMarkdown: string, title: string) {
  const pattern = new RegExp(`^####\\s+${title}\\s*$`, "m");
  const match = periodMarkdown.match(pattern);
  if (!match || match.index === undefined) {
    return [];
  }
  const start = match.index + match[0].length;
  const nextHeading = periodMarkdown.slice(start).search(/^####\s+/m);
  const block = nextHeading >= 0 ? periodMarkdown.slice(start, start + nextHeading) : periodMarkdown.slice(start);
  return block
    .split(/\r?\n/)
    .map((line) => line.replace(/^\s*[-*+]\s+/, "").trim())
    .filter(Boolean)
    .filter((line) => line !== "---")
    .filter(isMeaningfulReportItem);
}

function isMeaningfulReportItem(item: string) {
  const cleaned = item.trim();
  if (!cleaned) {
    return false;
  }
  const invalidFragments = [
    "暂无日报记录",
    "暂无可总结内容",
    "暂无可总结收获",
    "原始日报未体现明显问题",
    "原始日报未体现明确个人成长",
    "原始日报未提供更多细节",
    "原始日报未体现",
    "原始日报未详述",
    "具体修正方案原始日报未详述",
    "具体解决方案",
    "未体现明显问题",
    "未体现明确个人成长",
    "未详述",
  ];
  return !invalidFragments.some((fragment) => cleaned.includes(fragment));
}

function joinReportItems(items: string[], separator: string) {
  return uniqueReportItems(items).join(separator);
}

function uniqueReportItems(items: string[]) {
  const seen = new Set<string>();
  return items.filter((item) => {
    const cleaned = item.trim();
    if (!isMeaningfulReportItem(cleaned) || seen.has(cleaned)) {
      return false;
    }
    seen.add(cleaned);
    return true;
  });
}

function pairProblemsAndSolutions(problems: string[], solutions: string[]) {
  const cleanProblems = uniqueReportItems(problems);
  const cleanSolutions = uniqueReportItems(solutions);
  return cleanProblems.map((problem, index) => {
    const parts = [`问题：${problem}`];
    if (cleanSolutions[index]) {
      parts.push(`方案：${cleanSolutions[index]}`);
    }
    return `${index + 1}. ${parts.join("; ")}`;
  });
}

function buildWeeklySummary(markdown: string, parsed: Record<string, ParsedReportDay>) {
  const days = Object.values(parsed);
  const used = new Set<string>();
  const workItems = takeNovelItems(days.flatMap((day) => day.work), used, 4);
  const outputItems = takeNovelItems(days.flatMap((day) => day.work), used, 5);
  const solutions = takeNovelItems(days.flatMap((day) => day.solutions), used, 3);
  const gains = takeNovelItems([...days.flatMap((day) => day.growth), ...extractWeeklyGainItems(markdown)], used, 3);
  const problems = takeNovelItems(days.flatMap((day) => day.problems), used, 3);
  const summaryParts = [];
  if (workItems.length) {
    summaryParts.push(`本周工作主线聚焦于${joinSummaryItems(workItems)}`);
  }
  if (outputItems.length) {
    summaryParts.push(`主要产出包括${joinSummaryItems(outputItems)}`);
  }
  if (solutions.length) {
    summaryParts.push(`通过${joinSummaryItems(solutions)}推进问题处理和效果沉淀`);
  }
  if (gains.length) {
    summaryParts.push(`在业务场景思考和复盘上形成了${joinSummaryItems(gains)}等认识`);
  }
  if (problems.length) {
    summaryParts.push(`后续需要继续关注${joinSummaryItems(problems)}`);
  }
  return summaryParts.length ? `${summaryParts.join("；")}。` : "本周暂无足够内容形成总结。";
}

function extractWeeklyGainItems(markdown: string) {
  const match = markdown.match(/^##\s+本周收获\s*$/m);
  if (!match || match.index === undefined) {
    return [];
  }
  return markdown
    .slice(match.index + match[0].length)
    .split(/\r?\n/)
    .map((line) => line.replace(/^\s*[-*+]\s+/, "").trim())
    .filter(isMeaningfulReportItem);
}

function takeNovelItems(items: string[], used: Set<string>, limit: number) {
  const result: string[] = [];
  for (const item of uniqueReportItems(items)) {
    const topics = summaryTopics(item);
    if (topics.length === 0 || topics.some((topic) => used.has(topic))) {
      continue;
    }
    topics.forEach((topic) => used.add(topic));
    result.push(item);
    if (result.length >= limit) {
      break;
    }
  }
  return result;
}

function summaryTopics(item: string) {
  const normalized = normalizeSummaryText(item);
  const topics = topicPatterns
    .filter((pattern) => pattern.keywords.every((keyword) => normalized.includes(keyword)))
    .map((pattern) => pattern.topic);
  if (topics.length > 0) {
    return [...new Set(topics)];
  }
  return [normalized].filter(Boolean);
}

function normalizeSummaryText(item: string) {
  return item
    .replace(/[，。；;、\s（）()]/g, "")
    .replace(/^对/, "")
    .replace(/本周|主要|已经|进行|进行了|完成|修复|解决|新增|支持|思考|测试|部署|上线|重新|更加|更|比较|初步|熟悉|清晰|系统|流程|问题|方案|功能|服务/g, "")
    .trim()
    .toLowerCase();
}

const topicPatterns = [
  { topic: "stocksystem", keywords: ["stocksystem"] },
  { topic: "douyin-api-repeat", keywords: ["抖音", "重复"] },
  { topic: "douyin-api-publish", keywords: ["抖音", "发布"] },
  { topic: "douyin-api-comment", keywords: ["抖音", "评论"] },
  { topic: "podcast-system", keywords: ["播客"] },
  { topic: "podcast-persistence", keywords: ["播客", "持久化"] },
  { topic: "podcast-data-lifecycle", keywords: ["播客", "数据"] },
  { topic: "voice-id", keywords: ["音色"] },
  { topic: "speaker-count", keywords: ["讲话人"] },
  { topic: "consistency", keywords: ["一致性"] },
  { topic: "scheduled-delete", keywords: ["定时删除"] },
];

function joinSummaryItems(items: string[]) {
  return items.join("; ");
}

export function DailyNotesDashboard() {
  const [viewDate, setViewDate] = useState(() => new Date());
  const [selectedDate, setSelectedDate] = useState(() => toDateKey(new Date()));
  const [rangeStart, setRangeStart] = useState(() => toDateKey(new Date()));
  const [rangeEnd, setRangeEnd] = useState(() => toDateKey(new Date()));
  const [days, setDays] = useState<DailyNoteDay[]>([]);
  const [noteText, setNoteText] = useState("");
  const [period, setPeriod] = useState(() => currentPeriod());
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [generatingDaily, setGeneratingDaily] = useState(false);
  const [generatingWeekly, setGeneratingWeekly] = useState(false);
  const [dailyResult, setDailyResult] = useState<{ optimized_file?: string | null } | null>(null);
  const [weeklyResult, setWeeklyResult] = useState<NoteWeeklyRangeResult | null>(null);
  const [exportModalOpen, setExportModalOpen] = useState(false);
  const [exportFormat, setExportFormat] = useState<ExportFormat>("markdown");
  const [savingExport, setSavingExport] = useState(false);
  const [editing, setEditing] = useState<Record<string, string>>({});
  const [errorEntries, setErrorEntries] = useState<FloatingErrorEntry[]>([]);
  const [errorPopoverOpen, setErrorPopoverOpen] = useState(false);

  const selectedMonth = monthKey(viewDate);
  const cells = useMemo(() => buildMonthCells(viewDate), [viewDate]);
  const dayMap = useMemo(() => new Map(days.map((day) => [day.date, day])), [days]);
  const selectedDay = dayMap.get(selectedDate);
  const selectedRange = useMemo(() => normalizeRange(rangeStart, rangeEnd), [rangeStart, rangeEnd]);
  const rangeDaysWithNotes = useMemo(
    () => days.filter((day) => isDateInRange(day.date, selectedRange.from, selectedRange.to)),
    [days, selectedRange],
  );
  const isRangeMode = selectedRange.from !== selectedRange.to;

  const notifyError = (error: any, fallback: string) => {
    const errorMessage = getNotesErrorMessage(error, fallback);
    setErrorEntries((current) => [createFloatingErrorEntry(errorMessage), ...current].slice(0, 20));
    message.error(errorMessage);
  };

  const loadNotes = async () => {
    setLoading(true);
    try {
      const payload = await fetchDailyNotes(selectedMonth);
      setDays(payload.days);
    } catch (error: any) {
      notifyError(error, "Failed to load notes.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadNotes();
  }, [selectedMonth]);

  useEffect(() => {
    const nextEditing: Record<string, string> = {};
    selectedDay?.notes.forEach((note) => {
      nextEditing[note.id] = note.content;
    });
    setEditing(nextEditing);
  }, [selectedDay]);

  const addNote = async () => {
    setSaving(true);
    try {
      await createDailyNote({ content: noteText, date: selectedDate, period });
      setNoteText("");
      await loadNotes();
      message.success("Note saved.");
    } catch (error: any) {
      notifyError(error, "Failed to save note.");
    } finally {
      setSaving(false);
    }
  };

  const saveExisting = async (note: DailyNote) => {
    try {
      await updateDailyNote(note.id, { content: editing[note.id] || "", period: note.period });
      await loadNotes();
      message.success("Note updated.");
    } catch (error: any) {
      notifyError(error, "Failed to update note.");
    }
  };

  const removeNote = async (note: DailyNote) => {
    try {
      await deleteDailyNote(note.id);
      await loadNotes();
      message.success("Note deleted.");
    } catch (error: any) {
      notifyError(error, "Failed to delete note.");
    }
  };

  const generateDaily = async () => {
    setGeneratingDaily(true);
    try {
      const result = await generateDailyFromNotes(selectedDate);
      setDailyResult(result);
      message.success("Daily report generated.");
    } catch (error: any) {
      notifyError(error, "Failed to generate daily report.");
    } finally {
      setGeneratingDaily(false);
    }
  };

  const generateWeekly = async () => {
    setGeneratingWeekly(true);
    try {
      const result = isRangeMode ? await runWeeklyRangeTask() : await generateWeeklyFromNotes(selectedDate);
      setWeeklyResult(result);
      message.success(isRangeMode ? "Stage report generated." : "Weekly report generated.");
    } catch (error: any) {
      notifyError(error, "Failed to generate weekly report.");
    } finally {
      setGeneratingWeekly(false);
    }
  };

  const runWeeklyRangeTask = async () => {
    let task: NoteWeeklyRangeTaskResponse = await createWeeklyRangeTaskFromNotes({
      from_date: selectedRange.from,
      to_date: selectedRange.to,
    });
    message.loading({ content: "Stage report is running in background...", key: "note-weekly-range-task", duration: 0 });
    let pollCount = 0;
    let consecutivePollErrors = 0;
    while (true) {
      if (task.status === "completed" && task.result) {
        message.destroy("note-weekly-range-task");
        return task.result;
      }
      if (task.status === "failed") {
        message.destroy("note-weekly-range-task");
        throw new Error(task.error_message || "Stage report generation failed.");
      }
      await wait(3000);
      try {
        task = await fetchWeeklyRangeTaskFromNotes(task.task_id);
        consecutivePollErrors = 0;
        pollCount += 1;
        if (pollCount % 20 === 0) {
          message.loading({
            content: "Stage report is still running in background...",
            key: "note-weekly-range-task",
            duration: 0,
          });
        }
      } catch (error) {
        consecutivePollErrors += 1;
        if (consecutivePollErrors >= 5) {
          message.destroy("note-weekly-range-task");
          throw error;
        }
        message.loading({
          content: "Stage report is still running. Retrying status check...",
          key: "note-weekly-range-task",
          duration: 0,
        });
      }
    }
  };

  const saveWeeklyExport = async () => {
    if (!weeklyResult?.preview) {
      message.error("No report content to export.");
      return;
    }
    setSavingExport(true);
    try {
      const reportKind = isRangeMode ? "stage-report" : "weekly-report";
      const dateSlug = isRangeMode ? `${selectedRange.from}_to_${selectedRange.to}` : selectedDate;
      const csvColumns = collectCsvColumns(days, selectedRange.from, selectedRange.to);
      await saveReportToFile(
        buildExportContent(weeklyResult.preview, exportFormat, csvColumns),
        exportFormat,
        `${reportKind}_${dateSlug}`,
      );
      setExportModalOpen(false);
      message.success("Report saved.");
    } catch (error: any) {
      if (error?.name !== "AbortError") {
        notifyError(error, "Failed to save report.");
      }
    } finally {
      setSavingExport(false);
    }
  };

  const shiftMonth = (offset: number) => {
    setViewDate((current) => new Date(current.getFullYear(), current.getMonth() + offset, 1));
  };

  const selectCalendarDate = (date: string, shiftKey: boolean) => {
    setSelectedDate(date);
    if (shiftKey) {
      setRangeEnd(date);
      return;
    }
    setRangeStart(date);
    setRangeEnd(date);
  };

  const updateRangeStart = (date: string) => {
    setRangeStart(date);
    setSelectedDate(date);
  };

  const updateRangeEnd = (date: string) => {
    setRangeEnd(date);
    setSelectedDate(date);
  };

  return (
    <div className="notes-dashboard">
      <div className="note-action-rail">
        <div className="note-range-box">
          <Typography.Text strong>{isRangeMode ? "阶段范围" : "当前日期"}</Typography.Text>
          <Input size="small" type="date" value={rangeStart} onChange={(event) => updateRangeStart(event.target.value)} />
          <Input size="small" type="date" value={rangeEnd} onChange={(event) => updateRangeEnd(event.target.value)} />
          <Typography.Text type="secondary">
            {isRangeMode ? `${rangeDaysWithNotes.length} 天有便条` : selectedDate}
          </Typography.Text>
        </div>
        <Button
          type="primary"
          icon={<FileTextOutlined />}
          disabled={!selectedDay}
          loading={generatingDaily}
          onClick={generateDaily}
        >
          生成并优化日报
        </Button>
        <Button disabled={isRangeMode ? !rangeStart || !rangeEnd : !dailyResult} loading={generatingWeekly} onClick={generateWeekly}>
          {isRangeMode ? "生成并优化阶段报" : "生成并优化周报"}
        </Button>
        {weeklyResult?.preview ? (
          <Button icon={<DownloadOutlined />} onClick={() => setExportModalOpen(true)}>
            {isRangeMode ? "下载阶段报" : "下载周报"}
          </Button>
        ) : null}
      </div>

      <section className="glass-card note-compose">
        <div>
          <Typography.Text className="eyebrow">Daily note</Typography.Text>
          <Typography.Title level={3}>写一条便条，系统会自动绑定日期和上午/下午。</Typography.Title>
          <Typography.Text type="secondary">
            当前选择：{selectedDate} · {isRangeMode ? `${selectedRange.from} 至 ${selectedRange.to}` : "单日"} · {periodLabels[period]}
          </Typography.Text>
        </div>
        <Input.TextArea
          rows={5}
          value={noteText}
          onChange={(event) => setNoteText(event.target.value)}
          placeholder="写下今天发生了什么、卡点、推进进展或临时想到的成长总结。"
        />
        <Space wrap>
          <Select
            value={period}
            onChange={setPeriod}
            options={[
              { value: "morning", label: "上午" },
              { value: "afternoon", label: "下午" },
            ]}
          />
          <Button type="primary" icon={<SaveOutlined />} loading={saving} onClick={addNote}>
            保存便条
          </Button>
        </Space>
      </section>

      <section className="glass-card note-calendar-shell">
        <div className="note-calendar-head">
          <div>
            <Typography.Text className="eyebrow">Calendar</Typography.Text>
            <Typography.Title level={3}>{selectedMonth}</Typography.Title>
          </div>
          <Space>
            <Button onClick={() => shiftMonth(-1)}>上一月</Button>
            <Button onClick={() => shiftMonth(1)}>下一月</Button>
          </Space>
        </div>
        {loading ? (
          <div className="note-calendar-loading">
            <Spin />
          </div>
        ) : (
          <div className="note-calendar-grid">
            {weekdayLabels.map((label) => (
              <div className="note-weekday" key={label}>
                {label}
              </div>
            ))}
            {cells.map((cell) => {
              const key = toDateKey(cell);
              const day = dayMap.get(key);
              const isCurrentMonth = cell.getMonth() === viewDate.getMonth();
              const isInSelectedRange = isDateInRange(key, selectedRange.from, selectedRange.to);
              return (
                <Popover key={key} content={notePreview(day)} trigger="hover" placement="top">
                  <button
                    className={[
                      "note-day",
                      `note-day-level-${day?.detail_level || 0}`,
                      isCurrentMonth ? "" : "note-day-muted",
                      key === selectedDate ? "note-day-selected" : "",
                      isInSelectedRange ? "note-day-range-selected" : "",
                      isRangeMode && (key === selectedRange.from || key === selectedRange.to) ? "note-day-range-edge" : "",
                    ].join(" ")}
                    onClick={(event) => selectCalendarDate(key, event.shiftKey)}
                  >
                    <span>{cell.getDate()}</span>
                    {day ? <small>{day.note_count} note</small> : null}
                  </button>
                </Popover>
              );
            })}
          </div>
        )}
      </section>

      <section className="glass-card note-detail-page">
        <div className="note-detail-head">
          <div>
            <Typography.Text className="eyebrow">Selected date</Typography.Text>
            <Typography.Title level={3}>{selectedDate}</Typography.Title>
          </div>
          {dailyResult?.optimized_file ? <Tag color="green">日报已保存</Tag> : null}
        </div>
        {!selectedDay ? (
          <Empty description="这一天还没有便条，先在上方写一条。" />
        ) : (
          <div className="note-edit-list">
            {selectedDay.notes.map((note) => (
              <div className="note-edit-item" key={note.id}>
                <Space className="note-edit-meta" wrap>
                  <Tag color="green">{periodLabels[note.period] || note.period}</Tag>
                  <Typography.Text type="secondary">
                    {note.updated_at.replace("T", " ")} · 详细度 {note.detail_level}
                  </Typography.Text>
                </Space>
                <Input.TextArea
                  rows={4}
                  value={editing[note.id] ?? note.content}
                  onChange={(event) => setEditing((current) => ({ ...current, [note.id]: event.target.value }))}
                />
                <Space wrap>
                  <Button type="primary" onClick={() => saveExisting(note)}>
                    修改
                  </Button>
                  <Button danger onClick={() => removeNote(note)}>
                    删除
                  </Button>
                </Space>
              </div>
            ))}
          </div>
        )}
      </section>
      <FloatingErrorButton
        errors={errorEntries}
        open={errorPopoverOpen}
        onOpenChange={setErrorPopoverOpen}
        onClear={() => {
          setErrorEntries([]);
          setErrorPopoverOpen(false);
        }}
      />
      <Modal
        title={isRangeMode ? "下载阶段报" : "下载周报"}
        open={exportModalOpen}
        onCancel={() => setExportModalOpen(false)}
        onOk={saveWeeklyExport}
        confirmLoading={savingExport}
        okText="选择保存位置"
        cancelText="取消"
      >
        <Space direction="vertical" size="middle">
          <Radio.Group
            optionType="button"
            buttonStyle="solid"
            options={[...exportFormatOptions]}
            value={exportFormat}
            onChange={(event) => setExportFormat(event.target.value)}
          />
          <Typography.Text type="secondary">
            {isRangeMode ? `${selectedRange.from} 至 ${selectedRange.to}` : selectedDate}
          </Typography.Text>
        </Space>
      </Modal>
    </div>
  );
}
