import { decodeHTML } from "entities";
import { Parser } from "htmlparser2";

// Match Vale's native comment controls after HTML decoding, not prose mentions.
const valeControl =
  /^vale (?:on|off|styles? = [^\r\n]*|[^\r\n]+ = (?:YES|NO|on|off))$/u;

/** @type {import("markdownlint").Rule} */
const noProseControl = {
  names: ["no-prose-control"],
  description:
    "Prose rules are configured by the repository, not document comments",
  tags: ["comments"],
  parser: "micromark",
  function(params, onError) {
    const pending = [...params.parsers.micromark.tokens];
    while (pending.length) {
      const token = pending.pop();
      pending.push(...token.children);
      if (token.type === "htmlFlow" || token.type === "htmlText") {
        new Parser({
          oncomment(comment) {
            if (valeControl.test(decodeHTML(comment).trim())) {
              onError({
                lineNumber: token.startLine,
                detail:
                  "Remove the Vale control comment; correct prose or the governed vocabulary.",
              });
            }
          },
        }).end(token.text);
      }
    }
  },
};

// Upstream blank-line rules leave single-paragraph peer spacing unconstrained.
const spacingTokens = new Set([
  "lineEnding",
  "lineEndingBlank",
  "listItemIndent",
  "blockQuotePrefix",
  "linePrefix",
]);
/** @type {import("markdownlint").Rule} */
const singleParagraphListSpacing = {
  names: ["single-paragraph-list-spacing"],
  description: "Single-paragraph list items have no blank separators",
  tags: ["blank_lines"],
  parser: "micromark",
  function(params, onError) {
    const pending = [...params.parsers.micromark.tokens];
    while (pending.length) {
      const list = pending.pop();
      pending.push(...list.children);
      if (list.type !== "listOrdered" && list.type !== "listUnordered")
        continue;
      const items = [];
      for (const child of list.children) {
        if (child.type === "listItemPrefix") items.push([]);
        else if (items.length && !spacingTokens.has(child.type))
          items.at(-1).push(child);
      }
      if (
        items.length < 2 ||
        !items.every(
          (item) =>
            item.length === 1 &&
            item[0].type === "content" &&
            item[0].children.length === 1 &&
            item[0].children[0].type === "paragraph",
        )
      )
        continue;
      for (let index = 1; index < items.length; index++) {
        const lineNumber = items[index - 1][0].endLine + 1;
        if (lineNumber < items[index][0].startLine)
          onError({
            lineNumber,
            detail:
              "Remove the blank separator between single-paragraph items.",
            fixInfo: { lineNumber, deleteCount: -1 },
          });
      }
    }
  },
};

export default {
  config: {
    MD013: {
      line_length: 80,
      code_blocks: false,
      tables: false,
      headings: false,
    },
    MD024: { siblings_only: true },
  },
  noInlineConfig: true,
  customRules: [noProseControl, singleParagraphListSpacing],
};
