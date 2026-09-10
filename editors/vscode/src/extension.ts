import * as fs from "node:fs";
import * as path from "node:path";
import * as vscode from "vscode";
import {
  ExecuteCommandRequest,
  LanguageClient,
  LanguageClientOptions,
  ServerOptions,
  State,
} from "vscode-languageclient/node";

let client: LanguageClient | undefined;
let status: vscode.StatusBarItem | undefined;

export async function activate(context: vscode.ExtensionContext): Promise<void> {
  status = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
  status.text = "Almasix: starting…";
  status.show();
  context.subscriptions.push(status);

  context.subscriptions.push(
    vscode.commands.registerCommand("almasix.rebuildIndex", async () => {
      await ensureClient();
      const result = await client!.sendRequest(ExecuteCommandRequest.type, {
        command: "almasix.rebuildIndex",
        arguments: [],
      });
      void vscode.window.showInformationMessage(String(result ?? "Index rebuilt."));
    }),
    vscode.commands.registerCommand("almasix.showAppInfo", async () => {
      await ensureClient();
      const result = await client!.sendRequest(ExecuteCommandRequest.type, {
        command: "almasix.showAppInfo",
        arguments: [],
      });
      void vscode.window.showInformationMessage(String(result ?? "No app info."));
    }),
    vscode.commands.registerCommand("almasix.restartServer", async () => {
      await stopClient();
      await startClient(context);
      void vscode.window.showInformationMessage("Almasix language server restarted.");
    }),
  );

  await startClient(context);
}

export async function deactivate(): Promise<void> {
  await stopClient();
}

async function ensureClient(): Promise<void> {
  if (!client || client.state !== State.Running) {
    throw new Error("Almasix language server is not running. Check the status bar.");
  }
}

async function startClient(context: vscode.ExtensionContext): Promise<void> {
  const launch = resolveServerCommand();
  if (!launch) {
    if (status) {
      status.text = "Almasix: LSP missing";
      status.tooltip =
        "Install almasix[lsp] in the project venv, or set almasix.pythonPath / almasix.lsp.command.";
      status.backgroundColor = new vscode.ThemeColor("statusBarItem.errorBackground");
    }
    void vscode.window.showErrorMessage(
      "Almasix LSP not found. Install with: pip install 'almasix[lsp]' (in the workspace venv), then Almasix: Restart Language Server.",
    );
    return;
  }

  const serverOptions: ServerOptions = {
    command: launch.command,
    args: launch.args,
    options: { cwd: workspaceRoot() },
  };

  const clientOptions: LanguageClientOptions = {
    documentSelector: [
      { scheme: "file", language: "python" },
      { scheme: "file", language: "prism-html" },
      { scheme: "file", language: "html" },
    ],
    synchronize: {
      fileEvents: vscode.workspace.createFileSystemWatcher("**/*.{py,prism.html,html}"),
    },
  };

  client = new LanguageClient("almasix", "Almasix Language Server", serverOptions, clientOptions);
  context.subscriptions.push(client);

  client.onDidChangeState((event) => {
    if (!status) {
      return;
    }
    if (event.newState === State.Running) {
      status.text = "Almasix";
      status.tooltip = `LSP: ${launch.command} ${launch.args.join(" ")}`.trim();
      status.backgroundColor = undefined;
    } else if (event.newState === State.Starting) {
      status.text = "Almasix: starting…";
    } else {
      status.text = "Almasix: stopped";
    }
  });

  try {
    await client.start();
  } catch (err) {
    if (status) {
      status.text = "Almasix: LSP failed";
      status.backgroundColor = new vscode.ThemeColor("statusBarItem.errorBackground");
    }
    void vscode.window.showErrorMessage(`Almasix LSP failed to start: ${String(err)}`);
  }
}

async function stopClient(): Promise<void> {
  if (client) {
    await client.stop();
    client = undefined;
  }
}

function workspaceRoot(): string | undefined {
  return vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
}

function resolveServerCommand(): { command: string; args: string[] } | undefined {
  const cfg = vscode.workspace.getConfiguration("almasix");
  const override = (cfg.get<string>("lsp.command") || "").trim();
  const extra = cfg.get<string[]>("lsp.args") || [];
  if (override) {
    return { command: override, args: extra };
  }

  const python = resolvePython(cfg.get<string>("pythonPath") || "");
  const root = workspaceRoot();

  const candidates: Array<{ command: string; args: string[] }> = [];
  if (python) {
    candidates.push({ command: python, args: ["-m", "almasix.lsp", ...extra] });
    const binDir = path.dirname(python);
    const lspBin = path.join(binDir, process.platform === "win32" ? "almasix-lsp.exe" : "almasix-lsp");
    if (fs.existsSync(lspBin)) {
      candidates.unshift({ command: lspBin, args: [...extra] });
    }
  }
  if (root) {
    const venvPython = path.join(
      root,
      ".venv",
      process.platform === "win32" ? "Scripts/python.exe" : "bin/python",
    );
    if (fs.existsSync(venvPython)) {
      candidates.push({ command: venvPython, args: ["-m", "almasix.lsp", ...extra] });
      const venvLsp = path.join(
        root,
        ".venv",
        process.platform === "win32" ? "Scripts/almasix-lsp.exe" : "bin/almasix-lsp",
      );
      if (fs.existsSync(venvLsp)) {
        candidates.unshift({ command: venvLsp, args: [...extra] });
      }
    }
  }
  candidates.push({ command: "almasix-lsp", args: [...extra] });
  candidates.push({ command: "python", args: ["-m", "almasix.lsp", ...extra] });
  candidates.push({ command: "python3", args: ["-m", "almasix.lsp", ...extra] });

  for (const candidate of candidates) {
    if (candidate.command.includes(path.sep) || candidate.command.includes("/")) {
      if (fs.existsSync(candidate.command)) {
        return candidate;
      }
      continue;
    }
    // Bare command on PATH — let the OS resolve it.
    return candidate;
  }
  return undefined;
}

function resolvePython(configured: string): string | undefined {
  const root = workspaceRoot();
  let value = configured.trim();
  if (!value && root) {
    value = path.join(root, ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
  }
  if (!value) {
    return undefined;
  }
  value = value.replace(/\$\{workspaceFolder\}/g, root || "");
  if (fs.existsSync(value)) {
    return value;
  }
  return configured.trim() || undefined;
}
