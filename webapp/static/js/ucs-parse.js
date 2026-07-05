/** Lightweight offline UCS parser (UTF-16-LE, id<TAB>text). No WASM required. */

export function detectEncoding(bytes) {
  if (bytes.length >= 2 && bytes[0] === 0xff && bytes[1] === 0xfe) return { encoding: "utf-16-le", hasBom: true };
  if (bytes.length >= 2 && bytes[0] === 0xfe && bytes[1] === 0xff) return { encoding: "utf-16-be", hasBom: true };
  return { encoding: "utf-16-le", hasBom: false };
}

export function parseUcsBytes(bytes) {
  const { encoding, hasBom } = detectEncoding(bytes);
  const dec = new TextDecoder(encoding === "utf-16-be" ? "utf-16-be" : "utf-16-le");
  let text = dec.decode(bytes);
  if (hasBom && text.charCodeAt(0) === 0xfeff) text = text.slice(1);
  const entries = {};
  const invalid = [];
  const lines = text.split(/\r\n|\n|\r/);
  lines.forEach((line, idx) => {
    if (!line.trim()) return;
    const tab = line.indexOf("\t");
    if (tab < 0) {
      invalid.push({ line: idx + 1, reason: "no tab separator", raw: line });
      return;
    }
    const key = parseInt(line.slice(0, tab), 10);
    if (Number.isNaN(key)) {
      invalid.push({ line: idx + 1, reason: "non-numeric key", raw: line });
      return;
    }
    entries[key] = line.slice(tab + 1);
  });
  return { entries, invalid, encoding, hasBom };
}
