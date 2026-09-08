"""Translation service provider."""

from __future__ import annotations

from pathlib import Path

from avalon.providers.provider import ServiceProvider
from avalon.translation.helpers import set_translator
from avalon.translation.locale import set_fallback_locale
from avalon.translation.translator import Translator


def framework_lang_path() -> Path:
    return Path(__file__).resolve().parent / "lang"


class TranslationServiceProvider(ServiceProvider):
    """Binds the Translator and registers framework + app language paths."""

    def register(self) -> None:
        app = self.app

        def factory(_container):
            locale = str(app.config.get("app.locale", "en") or "en")
            fallback = str(app.config.get("app.fallback_locale", "en") or "en")
            translator = Translator(locale=locale, fallback=fallback)
            translator.add_path(framework_lang_path())
            translator.add_json_path(framework_lang_path())
            app_lang = app.path("lang")
            if app_lang.is_dir():
                translator.add_path(app_lang)
                translator.add_json_path(app_lang)
            return translator

        app.container.singleton(Translator, factory)
        app.container.alias(Translator, "translator")
        app.container.alias(Translator, "lang")

    def boot(self) -> None:
        translator = self.app.make(Translator)
        set_translator(translator)
        set_fallback_locale(translator.get_fallback())
        self.publishes({framework_lang_path(): self.app.path("lang")}, "avalon-lang")
        # Context locale stays unset until a request (or set_locale) pins it.
