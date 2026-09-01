"""Pass-based Python, C and Go source obfuscator."""

from .languages import SourceLanguage, detect_language
from .pipeline import ObfuscationConfig, Obfuscator

__all__ = ["ObfuscationConfig", "Obfuscator", "SourceLanguage", "detect_language"]
__version__ = "0.2.0"
