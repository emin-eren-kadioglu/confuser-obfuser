"""Pass-based Python, C and Go source obfuscator."""

from .languages import SourceLanguage, detect_language
from .pipeline import ObfuscationConfig, Obfuscator
from .project import ProjectResult, obfuscate_project

__all__ = ["ObfuscationConfig", "Obfuscator", "SourceLanguage", "detect_language", "ProjectResult", "obfuscate_project"]
__version__ = "0.3.0"
