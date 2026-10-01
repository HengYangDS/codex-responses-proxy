import assert from "node:assert/strict";
import test from "node:test";

import { lint } from "markdownlint/sync";

import policy from "../../.config/quality/native/markdownlint-cli2.mjs";

const cases = [
  ["ordinary prose", "Read the current source.\n", false],
  ["ordinary comment", "<!-- source: current -->\n", false],
  [
    "natural Vale comment",
    "<!-- vale is the prose checker, not policy. -->\n",
    false,
  ],
  [
    "natural rule comment",
    "<!-- vale spelling is useful for contributors. -->\n",
    false,
  ],
  [
    "natural mention",
    "The phrase vale off describes a disabled check.\n",
    false,
  ],
  ["inline code", "Read `<!-- vale off -->` as literal code.\n", false],
  ["fenced code", "```html\n<!-- vale off -->\n```\n", false],
  ["tilde fence", "~~~html\n<!-- vale off -->\n~~~\n", false],
  ["block control", "<!-- vale off -->\n", true],
  ["enabling control", "<!-- vale on -->\n", true],
  ["style-level control", "<!-- vale Vale = off -->\n", true],
  ["lowercase rule control", "<!-- vale Vale.Spelling = off -->\n", true],
  ["encoded letter", "<!-- v&#97;le off -->\n", true],
  ["encoded space", "<!-- vale&#32;off -->\n", true],
  ["rule control", "<!-- vale Vale.Repetition = NO -->\n", true],
  ["match control", '<!-- vale Vale.Repetition["the"] = NO -->\n', true],
  ["style control", "<!-- vale styles = Plain -->\n", true],
  ["multiline control", "<!--\nvale off\n-->\n", true],
  ["inline control", "Read the <!-- vale off -->the source.\n", true],
  ["quoted control", "> <!-- vale off -->\n", true],
  ["list control", "- <!-- vale off -->\n", true],
  ["table control", "| Rule |\n| --- |\n| <!-- vale off -->Read. |\n", true],
  ["adjacent comments", "<!-- source: current --><!-- vale off -->\n", true],
  ["raw HTML control", "<div><!-- vale off --></div>\n", true],
  ["attribute example", '<div title="&lt;!-- vale off --&gt;"></div>\n', false],
  ["comment explanation", "<!-- source: &lt;!-- vale off --&gt; -->\n", false],
  ["escaped example", "Read &lt;!-- vale off --&gt; as an example.\n", false],
  [
    "self-disabling attempt",
    "<!-- markdownlint-disable no-prose-control -->\n<!-- vale off -->\n",
    true,
  ],
];

for (const [name, source, forbidden] of cases) {
  test(name, () => {
    const errors = lint({
      strings: { fixture: source },
      config: { default: false, "no-prose-control": true },
      noInlineConfig: policy.noInlineConfig,
      customRules: policy.customRules,
    }).fixture;
    assert.equal(errors.length > 0, forbidden);
    for (const error of errors) {
      assert.deepEqual(error.ruleNames, ["no-prose-control"]);
      assert.ok(error.lineNumber >= 1);
    }
  });
}
