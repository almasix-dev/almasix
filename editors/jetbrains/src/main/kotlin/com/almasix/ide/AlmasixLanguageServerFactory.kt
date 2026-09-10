package com.almasix.ide

import com.intellij.openapi.project.Project
import com.redhat.devtools.lsp4ij.LanguageServerFactory
import com.redhat.devtools.lsp4ij.client.LanguageClientImpl
import com.redhat.devtools.lsp4ij.server.StreamConnectionProvider

class AlmasixLanguageServerFactory : LanguageServerFactory {
    override fun createConnectionProvider(project: Project): StreamConnectionProvider {
        return AlmasixLanguageServer(project)
    }

    override fun createLanguageClient(project: Project): LanguageClientImpl {
        return LanguageClientImpl(project)
    }
}
