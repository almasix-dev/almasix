package com.almasix.ide

import com.intellij.openapi.application.PathManager
import org.jetbrains.plugins.textmate.api.TextMateBundleProvider
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.StandardCopyOption

/**
 * Publishes the Prism TextMate bundle shipped under ``resources/textMate/prism``.
 */
class PrismTextMateBundleProvider : TextMateBundleProvider {
    override fun getBundles(): List<TextMateBundleProvider.PluginBundle> {
        val dest = Path.of(PathManager.getSystemPath(), "almasix-textmate", "prism")
        syncBundle(dest)
        return listOf(TextMateBundleProvider.PluginBundle("prism", dest))
    }

    private fun syncBundle(dest: Path) {
        Files.createDirectories(dest)
        Files.createDirectories(dest.resolve("syntaxes"))
        copyResource("textMate/prism/package.json", dest.resolve("package.json"))
        copyResource(
            "textMate/prism/language-configuration.json",
            dest.resolve("language-configuration.json"),
        )
        copyResource(
            "textMate/prism/syntaxes/prism.tmLanguage.json",
            dest.resolve("syntaxes/prism.tmLanguage.json"),
        )
    }

    private fun copyResource(resource: String, target: Path) {
        val stream = javaClass.classLoader.getResourceAsStream(resource) ?: return
        stream.use { input ->
            Files.copy(input, target, StandardCopyOption.REPLACE_EXISTING)
        }
    }
}
