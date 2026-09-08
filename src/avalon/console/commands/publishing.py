"""Publishing commands — ``make:lang``, ``lang:*``, and ``errors:publish``.

Publishing copies framework files into a project, so none of these needs a
booted application: they keep working in a directory that has no
``bootstrap/app.py`` yet, and they write relative to the working directory
Grail was invoked from.
"""

from __future__ import annotations

from pathlib import Path

from avalon.console.command import Command
from avalon.exceptions.publish import BUNDLES, ErrorsPublishError, publish_errors
from avalon.grail.lang_cmd import LangError, make_lang, missing_keys, publish_lang


class MakeLangCommand(Command):
    signature = (
        "make:lang {locale : Locale tag, e.g. en or sw} "
        "{--force : Overwrite an existing locale tree}"
    )
    description = "Create an empty lang/<locale>/ tree"
    boots_application = False

    def handle(self) -> int:
        root = Path.cwd()
        try:
            path = make_lang(self.argument("locale"), root, force=bool(self.option("force")))
        except LangError as exc:
            self.error(str(exc))
            return self.FAILURE
        self.success(f"Locale created: {path.relative_to(root)}")
        return self.SUCCESS


class LangPublishCommand(Command):
    signature = "lang:publish {--force : Overwrite existing published files}"
    description = "Publish framework language files into lang/"
    boots_application = False

    def handle(self) -> int:
        root = Path.cwd()
        try:
            path = publish_lang(root, force=bool(self.option("force")))
        except LangError as exc:
            self.error(str(exc))
            return self.FAILURE
        self.success(f"Language files published: {path.relative_to(root)}")
        return self.SUCCESS


class LangMissingCommand(Command):
    signature = (
        "lang:missing {--l|locale= : Target locale to compare} {--fallback=en : Fallback locale}"
    )
    description = "List keys present in the fallback locale but missing in the target"
    boots_application = False

    def handle(self) -> int:
        """Exits ``FAILURE`` when keys are missing, so CI can gate on it."""
        locale = self.option("locale")
        if not isinstance(locale, str) or not locale:
            self.error("Missing required option: --locale")
            return self.FAILURE
        missing = missing_keys(Path.cwd(), locale=locale, fallback=self.option("fallback"))
        if not missing:
            self.success("No missing keys.")
            return self.SUCCESS
        for key in missing:
            self.line(key)
        return self.FAILURE


class ErrorsPublishCommand(Command):
    signature = (
        f"errors:publish {{--b|bundle=default : View look: {', '.join(BUNDLES)}}} "
        "{--force : Overwrite existing published files}"
    )
    description = "Publish framework error views into resources/views/errors/"
    boots_application = False

    def handle(self) -> int:
        root = Path.cwd()
        bundle = self.option("bundle")
        try:
            path = publish_errors(root, bundle=bundle, force=bool(self.option("force")))
        except ErrorsPublishError as exc:
            self.error(str(exc))
            return self.FAILURE
        self.success(f"Error views published ({bundle}): {path.relative_to(root)}")
        return self.SUCCESS
