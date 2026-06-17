from dataclasses import dataclass
from typing import Optional

@dataclass
class NormalizerRules:
  lowercase: bool
  trim_spaces: bool
  normalize_quotes: bool
  normalize_dashes: bool
