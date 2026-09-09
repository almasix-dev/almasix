package com.almasix.ide

import com.intellij.execution.Executor
import com.intellij.execution.configurations.CommandLineState
import com.intellij.execution.configurations.ConfigurationFactory
import com.intellij.execution.configurations.ConfigurationTypeBase
import com.intellij.execution.configurations.GeneralCommandLine
import com.intellij.execution.configurations.RunConfiguration
import com.intellij.execution.configurations.RunConfigurationBase
import com.intellij.execution.configurations.RunConfigurationOptions
import com.intellij.execution.configurations.RunProfileState
import com.intellij.execution.process.ProcessHandler
import com.intellij.execution.process.ProcessHandlerFactory
import com.intellij.execution.process.ProcessTerminatedListener
import com.intellij.execution.runners.ExecutionEnvironment
import com.intellij.openapi.options.SettingsEditor
import com.intellij.openapi.project.Project
import com.intellij.openapi.project.guessProjectDir
import com.intellij.openapi.util.NotNullLazyValue
import com.intellij.ui.components.JBTextField
import com.intellij.util.ui.FormBuilder
import java.nio.file.Files
import javax.swing.JComponent
import javax.swing.JPanel

class SmithConfigurationType : ConfigurationTypeBase(
    "AlmasixSmith",
    "Almasix Smith",
    "Run a Smith CLI command",
    NotNullLazyValue.createValue { PrismFileType.INSTANCE.icon },
) {
    init {
        addFactory(SmithConfigurationFactory(this))
    }
}

class SmithConfigurationFactory(type: SmithConfigurationType) : ConfigurationFactory(type) {
    override fun getId(): String = "AlmasixSmithFactory"

    override fun createTemplateConfiguration(project: Project): RunConfiguration {
        return SmithRunConfiguration(project, this, "smith serve")
    }
}

class SmithRunConfiguration(
    project: Project,
    factory: ConfigurationFactory,
    name: String,
) : RunConfigurationBase<RunConfigurationOptions>(project, factory, name) {

    var smithArgs: String = "serve"

    override fun getConfigurationEditor(): SettingsEditor<out RunConfiguration> {
        return SmithSettingsEditor()
    }

    override fun getState(executor: Executor, environment: ExecutionEnvironment): RunProfileState {
        return object : CommandLineState(environment) {
            override fun startProcess(): ProcessHandler {
                val root = project.guessProjectDir()?.toNioPath()
                val args = smithArgs.split(" ").filter { it.isNotBlank() }
                val cmd = buildSmithCommand(root, args)
                if (root != null) {
                    cmd.withWorkDirectory(root.toFile())
                }
                val handler = ProcessHandlerFactory.getInstance().createColoredProcessHandler(cmd)
                ProcessTerminatedListener.attach(handler)
                return handler
            }
        }
    }
}

class SmithSettingsEditor : SettingsEditor<SmithRunConfiguration>() {
    private val argsField = JBTextField("serve")

    override fun resetEditorFrom(configuration: SmithRunConfiguration) {
        argsField.text = configuration.smithArgs
    }

    override fun applyEditorTo(configuration: SmithRunConfiguration) {
        configuration.smithArgs = argsField.text.trim()
    }

    override fun createEditor(): JComponent {
        return FormBuilder.createFormBuilder()
            .addLabeledComponent("Smith arguments", argsField)
            .addComponentFillVertically(JPanel(), 0)
            .panel
    }
}

internal fun buildSmithCommand(root: java.nio.file.Path?, args: List<String>): GeneralCommandLine {
    if (root != null) {
        val venvSmith = root.resolve(".venv/bin/smith")
        if (Files.isExecutable(venvSmith)) {
            return GeneralCommandLine(venvSmith.toString()).withParameters(args)
        }
        val smithScript = root.resolve("smith")
        val python = root.resolve(".venv/bin/python")
        if (Files.isRegularFile(smithScript) && Files.isExecutable(python)) {
            return GeneralCommandLine(python.toString(), smithScript.toString()).withParameters(args)
        }
        if (Files.isRegularFile(smithScript)) {
            return GeneralCommandLine("python", smithScript.toString()).withParameters(args)
        }
    }
    return GeneralCommandLine("smith").withParameters(args)
}
