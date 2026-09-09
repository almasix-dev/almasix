package com.almasix.ide

import com.intellij.execution.configurations.GeneralCommandLine
import com.intellij.openapi.project.Project
import com.intellij.openapi.project.guessProjectDir
import com.redhat.devtools.lsp4ij.server.ProcessStreamConnectionProvider
import java.nio.file.Files
import java.nio.file.Path

/**
 * Starts ``almasix-lsp`` (or ``python -m almasix.lsp``) from the project venv.
 */
class AlmasixLanguageServer(private val project: Project) : ProcessStreamConnectionProvider() {
    init {
        val root = project.guessProjectDir()?.toNioPath()
        val command = resolveCommand(root)
        super.setCommands(command)
        if (root != null) {
            super.setWorkingDirectory(root.toString())
        }
    }

    companion object {
        fun resolveCommand(root: Path?): List<String> {
            if (root != null) {
                val venvLsp = root.resolve(".venv/bin/almasix-lsp")
                if (Files.isExecutable(venvLsp)) {
                    return listOf(venvLsp.toString())
                }
                val venvPython = root.resolve(".venv/bin/python")
                if (Files.isExecutable(venvPython)) {
                    return listOf(venvPython.toString(), "-m", "almasix.lsp")
                }
                val winLsp = root.resolve(".venv/Scripts/almasix-lsp.exe")
                if (Files.isRegularFile(winLsp)) {
                    return listOf(winLsp.toString())
                }
            }
            return listOf("almasix-lsp")
        }
    }
}
