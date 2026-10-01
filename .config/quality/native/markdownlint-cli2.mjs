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
  customRules: [noProseControl],
};
