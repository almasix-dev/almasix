plugins {
    id("java")
    id("org.jetbrains.kotlin.jvm") version "1.9.25"
    id("org.jetbrains.intellij.platform") version "2.1.0"
}

group = providers.gradleProperty("pluginGroup").get()
version = providers.gradleProperty("pluginVersion").get()

repositories {
    mavenCentral()
    intellijPlatform {
        defaultRepositories()
    }
}

dependencies {
    intellijPlatform {
        create(
            providers.gradleProperty("platformType"),
            providers.gradleProperty("platformVersion"),
        )
        bundledPlugin("com.intellij.java")
        bundledPlugin("org.jetbrains.plugins.textmate")
        // LSP client used to talk to almasix-lsp (Marketplace plugin id).
        plugin("com.redhat.devtools.lsp4ij", "0.14.0")
        instrumentationTools()
    }
}

kotlin {
    jvmToolchain(17)
}

intellijPlatform {
    pluginConfiguration {
        id = "com.almasix.ide"
        name = providers.gradleProperty("pluginName")
        version = providers.gradleProperty("pluginVersion")
        ideaVersion {
            sinceBuild = "242"
            untilBuild = provider { null }
        }
        description.set(
            """
            Almasix Prism file type, TextMate highlighting, Smith run configs,
            and LSP-first intelligence via almasix-lsp (LSP4IJ).
            Sideload with Install Plugin from Disk — Marketplace publish later.
            """.trimIndent(),
        )
        changeNotes.set(
            """
            <ul>
              <li>0.1.0 — M47: Prism file type, TextMate bundle, LSP4IJ → almasix-lsp, Smith run configs</li>
            </ul>
            """.trimIndent(),
        )
    }
}

tasks {
    wrapper {
        gradleVersion = providers.gradleProperty("gradleVersion").get()
    }
}
