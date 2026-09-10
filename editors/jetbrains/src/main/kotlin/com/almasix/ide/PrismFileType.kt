package com.almasix.ide

import com.intellij.openapi.fileTypes.LanguageFileType
import com.intellij.openapi.fileTypes.PlainTextLikeFileType
import com.intellij.openapi.util.IconLoader
import org.jetbrains.plugins.textmate.TextMateBackedFileType
import javax.swing.Icon

object PrismLanguage : com.intellij.lang.Language("Prism") {
    private fun readResolve(): Any = PrismLanguage
}

/**
 * Prism templates (``.prism.html``).
 *
 * Implements [TextMateBackedFileType] so IntelliJ's TextMate plugin will apply
 * the bundled grammar (same path as importing a VS Code extension). Without
 * that marker, claiming the file type leaves the buffer unhighlighted.
 */
class PrismFileType private constructor() :
    LanguageFileType(PrismLanguage),
    TextMateBackedFileType,
    PlainTextLikeFileType {
    override fun getName(): String = "Prism"

    override fun getDescription(): String = "Almasix Prism template (.prism.html)"

    override fun getDefaultExtension(): String = "prism.html"

    override fun getIcon(): Icon = IconLoader.getIcon("/icons/prism.svg", PrismFileType::class.java)

    companion object {
        @JvmField
        val INSTANCE = PrismFileType()
    }
}
