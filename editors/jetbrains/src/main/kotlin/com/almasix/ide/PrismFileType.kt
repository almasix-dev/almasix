package com.almasix.ide

import com.intellij.openapi.fileTypes.LanguageFileType
import com.intellij.openapi.util.IconLoader
import javax.swing.Icon

object PrismLanguage : com.intellij.lang.Language("Prism") {
    private fun readResolve(): Any = PrismLanguage
}

class PrismFileType private constructor() : LanguageFileType(PrismLanguage) {
    override fun getName(): String = "Prism"
    override fun getDescription(): String = "Almasix Prism template (.prism.html)"
    override fun getDefaultExtension(): String = "prism.html"
    override fun getIcon(): Icon = IconLoader.getIcon("/icons/prism.svg", PrismFileType::class.java)

    companion object {
        @JvmField
        val INSTANCE = PrismFileType()
    }
}
