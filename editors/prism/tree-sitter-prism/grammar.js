/**
 * Minimal tree-sitter grammar for Prism (``.prism.html``).
 *
 * Recognizes comments, echoes, raw echoes, directives, and HTML text.
 * Build (optional — not required for Almasix CI):
 *
 *   npm install -g tree-sitter-cli
 *   cd editors/prism/tree-sitter-prism
 *   tree-sitter generate
 *   tree-sitter build
 *
 * See ``../README.md`` for editor wiring.
 */

module.exports = grammar({
  name: "prism",

  extras: ($) => [/\s+/],

  rules: {
    source_file: ($) => repeat($._node),

    _node: ($) =>
      choice($.comment, $.echo, $.raw_echo, $.directive, $.html_text),

    comment: ($) => seq("{{--", /[\s\S]*?/, "--}}"),

    echo: ($) => seq("{{", /[\s\S]*?/, "}}"),

    raw_echo: ($) => seq("{!!", /[\s\S]*?/, "!!}"),

    directive: ($) =>
      seq(
        "@",
        field(
          "name",
          /[A-Za-z_][\w]*/
        ),
        optional(seq("(", /[^)]*/, ")"))
      ),

    html_text: ($) => /[^@{]+|[@{]/
  },
});
