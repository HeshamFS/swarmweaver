import React from "react";

// ── Token types ──

export type TokenType =
  | "keyword"
  | "string"
  | "comment"
  | "number"
  | "operator"
  | "function"
  | "type"
  | "punctuation"
  | "plain";

export interface Token {
  type: TokenType;
  value: string;
}

// ── Language detection ──

const EXT_MAP: Record<string, string> = {
  js: "javascript",
  jsx: "javascript",
  ts: "typescript",
  tsx: "typescript",
  mjs: "javascript",
  cjs: "javascript",
  py: "python",
  json: "json",
  css: "css",
  scss: "css",
  html: "html",
  htm: "html",
  xml: "html",
  svg: "html",
  md: "plain",
  txt: "plain",
  sh: "bash",
  bash: "bash",
  zsh: "bash",
  yml: "yaml",
  yaml: "yaml",
  toml: "toml",
  rs: "rust",
  go: "go",
};

export function detectLanguage(filename: string): string {
  const ext = filename.split(".").pop()?.toLowerCase() || "";
  return EXT_MAP[ext] || "plain";
}

// ── Language rules ──

interface LanguageRule {
  pattern: RegExp;
  type: TokenType;
}

const JS_TS_KEYWORDS =
  /\b(const|let|var|function|return|if|else|for|while|do|switch|case|break|continue|new|delete|typeof|instanceof|in|of|class|extends|import|export|from|default|try|catch|finally|throw|async|await|yield|void|this|super|true|false|null|undefined)\b/;
const TS_TYPES =
  /\b(string|number|boolean|any|void|never|unknown|object|interface|type|enum|namespace|declare|readonly|keyof|infer|extends)\b/;

const jsRules: LanguageRule[] = [
  { pattern: /(\/\/[^\n]*)/, type: "comment" },
  { pattern: /(\/\*[\s\S]*?\*\/)/, type: "comment" },
  { pattern: /("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|`(?:[^`\\]|\\.)*`)/, type: "string" },
  { pattern: /\b(\d+\.?\d*(?:[eE][+-]?\d+)?)\b/, type: "number" },
  { pattern: JS_TS_KEYWORDS, type: "keyword" },
  { pattern: /\b([A-Z]\w*)\b/, type: "type" },
  { pattern: /\b(\w+)(?=\s*\()/, type: "function" },
  { pattern: /([{}()[\];,.:?!<>=+\-*/%&|^~@#])/, type: "punctuation" },
];

const tsRules: LanguageRule[] = [
  { pattern: /(\/\/[^\n]*)/, type: "comment" },
  { pattern: /(\/\*[\s\S]*?\*\/)/, type: "comment" },
  { pattern: /("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|`(?:[^`\\]|\\.)*`)/, type: "string" },
  { pattern: /\b(\d+\.?\d*(?:[eE][+-]?\d+)?)\b/, type: "number" },
  { pattern: TS_TYPES, type: "type" },
  { pattern: JS_TS_KEYWORDS, type: "keyword" },
  { pattern: /\b([A-Z]\w*)\b/, type: "type" },
  { pattern: /\b(\w+)(?=\s*\()/, type: "function" },
  { pattern: /([{}()[\];,.:?!<>=+\-*/%&|^~@#])/, type: "punctuation" },
];

const PY_KEYWORDS =
  /\b(def|class|if|elif|else|for|while|return|import|from|as|try|except|finally|raise|with|yield|lambda|pass|break|continue|and|or|not|is|in|True|False|None|self|global|nonlocal|assert|del|async|await)\b/;

const pyRules: LanguageRule[] = [
  { pattern: /(#[^\n]*)/, type: "comment" },
  { pattern: /("""[\s\S]*?"""|'''[\s\S]*?''')/, type: "string" },
  { pattern: /("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')/, type: "string" },
  { pattern: /\b(\d+\.?\d*(?:[eE][+-]?\d+)?)\b/, type: "number" },
  { pattern: PY_KEYWORDS, type: "keyword" },
  { pattern: /\b([A-Z]\w*)\b/, type: "type" },
  { pattern: /\b(\w+)(?=\s*\()/, type: "function" },
  { pattern: /([{}()[\];,.:=+\-*/%&|^~@<>!])/, type: "punctuation" },
];

const jsonRules: LanguageRule[] = [
  { pattern: /("(?:[^"\\]|\\.)*")(?=\s*:)/, type: "function" },
  { pattern: /("(?:[^"\\]|\\.)*")/, type: "string" },
  { pattern: /\b(\d+\.?\d*(?:[eE][+-]?\d+)?)\b/, type: "number" },
  { pattern: /\b(true|false|null)\b/, type: "keyword" },
  { pattern: /([{}[\],:])/, type: "punctuation" },
];

const cssRules: LanguageRule[] = [
  { pattern: /(\/\*[\s\S]*?\*\/)/, type: "comment" },
  { pattern: /("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')/, type: "string" },
  { pattern: /\b(\d+\.?\d*(?:px|em|rem|%|vh|vw|deg|s|ms)?)\b/, type: "number" },
  { pattern: /([@#.]\w[\w-]*)/, type: "function" },
  { pattern: /\b(import|media|keyframes|font-face|charset|supports)\b/, type: "keyword" },
  { pattern: /([{}();:,!])/, type: "punctuation" },
];

const htmlRules: LanguageRule[] = [
  { pattern: /(<!--[\s\S]*?-->)/, type: "comment" },
  { pattern: /("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')/, type: "string" },
  { pattern: /(<\/?)([\w-]+)/, type: "keyword" },
  { pattern: /\b([\w-]+)(?==)/, type: "function" },
  { pattern: /([<>\/=!])/, type: "punctuation" },
];

const LANGUAGE_RULES: Record<string, LanguageRule[]> = {
  javascript: jsRules,
  typescript: tsRules,
  python: pyRules,
  json: jsonRules,
  css: cssRules,
  html: htmlRules,
};

// ── Tokenizer ──

export function tokenize(code: string, language: string): Token[] {
  const rules = LANGUAGE_RULES[language];
  if (!rules) {
    return [{ type: "plain", value: code }];
  }

  const tokens: Token[] = [];
  let remaining = code;

  while (remaining.length > 0) {
    let bestMatch: { index: number; length: number; type: TokenType; value: string } | null = null;

    for (const rule of rules) {
      const match = remaining.match(rule.pattern);
      if (match && match.index !== undefined) {
        const matchValue = match[1] || match[0];
        const matchIndex = remaining.indexOf(matchValue, match.index);
        if (
          !bestMatch ||
          matchIndex < bestMatch.index ||
          (matchIndex === bestMatch.index && matchValue.length > bestMatch.length)
        ) {
          bestMatch = {
            index: matchIndex,
            length: matchValue.length,
            type: rule.type,
            value: matchValue,
          };
        }
      }
    }

    if (bestMatch && bestMatch.index >= 0) {
      // Add plain text before the match
      if (bestMatch.index > 0) {
        tokens.push({ type: "plain", value: remaining.slice(0, bestMatch.index) });
      }
      tokens.push({ type: bestMatch.type, value: bestMatch.value });
      remaining = remaining.slice(bestMatch.index + bestMatch.length);
    } else {
      // No more matches
      tokens.push({ type: "plain", value: remaining });
      break;
    }
  }

  return tokens;
}

// ── Token type to CSS class mapping ──

const TOKEN_CLASSES: Record<TokenType, string> = {
  keyword: "syn-keyword",
  string: "syn-string",
  comment: "syn-comment",
  number: "syn-number",
  operator: "syn-operator",
  function: "syn-function",
  type: "syn-type",
  punctuation: "syn-punctuation",
  plain: "",
};

// ── Highlight to React spans ──

export function highlightToSpans(code: string, language: string): React.ReactNode[] {
  const tokens = tokenize(code, language);
  return tokens.map((token, i) => {
    const cls = TOKEN_CLASSES[token.type];
    if (!cls) {
      return token.value;
    }
    return React.createElement("span", { key: i, className: cls }, token.value);
  });
}
