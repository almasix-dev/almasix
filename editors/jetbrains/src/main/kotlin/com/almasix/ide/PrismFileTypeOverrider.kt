package com.almasix.ide

import com.intellij.openapi.fileTypes.FileType
import com.intellij.openapi.fileTypes.impl.FileTypeOverrider
import com.intellij.openapi.vfs.VirtualFile

/**
 * Force ``*.prism.html`` onto the Prism file type.
 *
 * IntelliJ's built-in HTML type claims ``*.html``, which otherwise wins for
 * compound names like ``welcome.prism.html`` and leaves only HTML highlighting.
 */
class PrismFileTypeOverrider : FileTypeOverrider {
    override fun getOverriddenFileType(file: VirtualFile): FileType? {
        val name = file.name
        if (name.endsWith(".prism.html", ignoreCase = true)) {
            return PrismFileType.INSTANCE
        }
        return null
    }
}
