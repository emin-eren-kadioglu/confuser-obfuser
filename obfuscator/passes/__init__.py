"""Built-in obfuscation passes."""

from .base import ObfuscationPass
from .encode_strings import EncodeStringsPass
from .insert_dead_code import InsertDeadCodePass
from .rename_identifiers import RenameIdentifiersPass
from .transform_numbers import TransformNumbersPass

__all__ = [
    "ObfuscationPass",
    "EncodeStringsPass",
    "InsertDeadCodePass",
    "RenameIdentifiersPass",
    "TransformNumbersPass",
]
