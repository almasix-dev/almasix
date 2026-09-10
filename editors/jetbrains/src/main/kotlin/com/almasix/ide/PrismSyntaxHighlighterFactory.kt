package com.almasix.ide

import com.intellij.lexer.Lexer
import com.intellij.lexer.LexerBase
import com.intellij.openapi.editor.DefaultLanguageHighlighterColors
import com.intellij.openapi.editor.colors.TextAttributesKey
import com.intellij.openapi.fileTypes.SyntaxHighlighter
import com.intellij.openapi.fileTypes.SyntaxHighlighterBase
import com.intellij.openapi.fileTypes.SyntaxHighlighterFactory
import com.intellij.openapi.project.Project
import com.intellij.openapi.vfs.VirtualFile
import com.intellij.psi.tree.IElementType
import com.intellij.psi.tree.TokenSet

/**
 * Native Prism highlighter — does not depend on TextMate filename matching.
 *
 * TextMate bundles are still shipped for preferences / future use, but compound
 * ``*.prism.html`` files often never receive a TextMate language descriptor
 * (HTML wins, or the extension peel stops at ``html``). A first-party lexer
 * keeps ``@if`` / ``{{ }}`` / comments visibly colored.
 */
class PrismSyntaxHighlighterFactory : SyntaxHighlighterFactory() {
    override fun getSyntaxHighlighter(project: Project?, virtualFile: VirtualFile?): SyntaxHighlighter {
        return PrismSyntaxHighlighter
    }
}

private object PrismSyntaxHighlighter : SyntaxHighlighterBase() {
    override fun getHighlightingLexer(): Lexer = PrismHighlightingLexer()

    override fun getTokenHighlights(tokenType: IElementType): Array<TextAttributesKey> {
        return when (tokenType) {
            PrismTokens.COMMENT -> COMMENT_KEYS
            PrismTokens.ECHO, PrismTokens.RAW_ECHO -> ECHO_KEYS
            PrismTokens.DIRECTIVE -> DIRECTIVE_KEYS
            PrismTokens.TAG -> TAG_KEYS
            PrismTokens.ATTR_NAME -> ATTR_NAME_KEYS
            PrismTokens.ATTR_VALUE -> ATTR_VALUE_KEYS
            else -> emptyArray()
        }
    }

    private val COMMENT_KEYS = arrayOf(PrismColors.COMMENT)
    private val ECHO_KEYS = arrayOf(PrismColors.ECHO)
    private val DIRECTIVE_KEYS = arrayOf(PrismColors.DIRECTIVE)
    private val TAG_KEYS = arrayOf(PrismColors.TAG)
    private val ATTR_NAME_KEYS = arrayOf(PrismColors.ATTR_NAME)
    private val ATTR_VALUE_KEYS = arrayOf(PrismColors.ATTR_VALUE)
}

object PrismColors {
    val COMMENT = TextAttributesKey.createTextAttributesKey(
        "PRISM_COMMENT",
        DefaultLanguageHighlighterColors.BLOCK_COMMENT,
    )
    val ECHO = TextAttributesKey.createTextAttributesKey(
        "PRISM_ECHO",
        DefaultLanguageHighlighterColors.TEMPLATE_LANGUAGE_COLOR,
    )
    val DIRECTIVE = TextAttributesKey.createTextAttributesKey(
        "PRISM_DIRECTIVE",
        DefaultLanguageHighlighterColors.KEYWORD,
    )
    val TAG = TextAttributesKey.createTextAttributesKey(
        "PRISM_TAG",
        DefaultLanguageHighlighterColors.KEYWORD,
    )
    val ATTR_NAME = TextAttributesKey.createTextAttributesKey(
        "PRISM_ATTR_NAME",
        DefaultLanguageHighlighterColors.INSTANCE_FIELD,
    )
    val ATTR_VALUE = TextAttributesKey.createTextAttributesKey(
        "PRISM_ATTR_VALUE",
        DefaultLanguageHighlighterColors.STRING,
    )
}

object PrismTokens {
    val COMMENT = IElementType("PRISM_COMMENT", PrismLanguage)
    val ECHO = IElementType("PRISM_ECHO", PrismLanguage)
    val RAW_ECHO = IElementType("PRISM_RAW_ECHO", PrismLanguage)
    val DIRECTIVE = IElementType("PRISM_DIRECTIVE", PrismLanguage)
    val TAG = IElementType("PRISM_TAG", PrismLanguage)
    val ATTR_NAME = IElementType("PRISM_ATTR_NAME", PrismLanguage)
    val ATTR_VALUE = IElementType("PRISM_ATTR_VALUE", PrismLanguage)
    val TEXT = IElementType("PRISM_TEXT", PrismLanguage)

    val ALL = TokenSet.create(COMMENT, ECHO, RAW_ECHO, DIRECTIVE, TAG, ATTR_NAME, ATTR_VALUE, TEXT)
}

/**
 * Lightweight scanner for Prism overlays on HTML-ish text.
 *
 * Priority: comment → raw echo → echo → directive → HTML tag / attributes → text.
 */
class PrismHighlightingLexer : LexerBase() {
    private var buffer: CharSequence = ""
    private var startOffset = 0
    private var endOffset = 0
    private var tokenStart = 0
    private var tokenEnd = 0
    private var tokenType: IElementType? = null

    override fun start(buffer: CharSequence, startOffset: Int, endOffset: Int, initialState: Int) {
        this.buffer = buffer
        this.startOffset = startOffset
        this.endOffset = endOffset
        this.tokenStart = startOffset
        this.tokenEnd = startOffset
        advance()
    }

    override fun getState(): Int = 0

    override fun getTokenType(): IElementType? = tokenType

    override fun getTokenStart(): Int = tokenStart

    override fun getTokenEnd(): Int = tokenEnd

    override fun getBufferSequence(): CharSequence = buffer

    override fun getBufferEnd(): Int = endOffset

    override fun advance() {
        tokenStart = tokenEnd
        if (tokenStart >= endOffset) {
            tokenType = null
            return
        }

        val text = buffer
        val i = tokenStart

        // {{-- comment --}}
        if (match(text, i, "{{--")) {
            val close = indexOf(text, i + 4, "--}}")
            tokenEnd = if (close >= 0) close + 4 else endOffset
            tokenType = PrismTokens.COMMENT
            return
        }

        // {!! raw !!}
        if (match(text, i, "{!!")) {
            val close = indexOf(text, i + 3, "!!}")
            tokenEnd = if (close >= 0) close + 3 else endOffset
            tokenType = PrismTokens.RAW_ECHO
            return
        }

        // {{ echo }}
        if (match(text, i, "{{") && !match(text, i, "{{--")) {
            val close = indexOf(text, i + 2, "}}")
            tokenEnd = if (close >= 0) close + 2 else endOffset
            tokenType = PrismTokens.ECHO
            return
        }

        // @directive (not @@ escape)
        if (text[i] == '@' && i + 1 < endOffset && text[i + 1] != '@' && isIdentStart(text[i + 1])) {
            var j = i + 1
            while (j < endOffset && isIdentPart(text[j])) j++
            tokenEnd = j
            tokenType = PrismTokens.DIRECTIVE
            return
        }

        // HTML tag: <tag ...> or </tag>
        if (text[i] == '<' && i + 1 < endOffset && (isIdentStart(text[i + 1]) || text[i + 1] == '/')) {
            scanTag(text, i)
            return
        }

        // plain text until next special
        var j = i + 1
        while (j < endOffset) {
            val c = text[j]
            if (c == '{' || c == '@' || c == '<') break
            j++
        }
        tokenEnd = j
        tokenType = PrismTokens.TEXT
    }

    private fun scanTag(text: CharSequence, start: Int) {
        // Emit the whole tag as TAG for simplicity (good enough for presence).
        var j = start + 1
        var inQuote: Char? = null
        while (j < endOffset) {
            val c = text[j]
            if (inQuote != null) {
                if (c == inQuote) inQuote = null
            } else {
                when (c) {
                    '"', '\'' -> inQuote = c
                    '>' -> {
                        tokenEnd = j + 1
                        tokenType = PrismTokens.TAG
                        return
                    }
                }
            }
            j++
        }
        tokenEnd = endOffset
        tokenType = PrismTokens.TAG
    }

    private fun match(text: CharSequence, offset: Int, literal: String): Boolean {
        if (offset + literal.length > endOffset) return false
        for (k in literal.indices) {
            if (text[offset + k] != literal[k]) return false
        }
        return true
    }

    private fun indexOf(text: CharSequence, from: Int, literal: String): Int {
        val last = endOffset - literal.length
        var i = from
        while (i <= last) {
            if (match(text, i, literal)) return i
            i++
        }
        return -1
    }

    private fun isIdentStart(c: Char): Boolean =
        c == '_' || c.isLetter()

    private fun isIdentPart(c: Char): Boolean =
        c == '_' || c == '-' || c.isLetterOrDigit()
}
