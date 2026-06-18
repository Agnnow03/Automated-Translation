import yaml
from ..domain.models.normalizer_rules import NormalizerRules
import string
import os


class Normalizer:

    def normalize(self, text: str, profile: str = "exact") -> str:
        self.normalizer_rules = self.load_normalizer_configuration()

        if profile == "exact":
            return self._normalize_exact(text)

        if profile == "fuzzy":
            return self._normalize_fuzzy(text)

        raise ValueError(
            f"Unknown profile: {profile}"
        )

    def load_normalizer_configuration(self) -> NormalizerRules:
        # Build an absolute path relative to this file so working directory doesn't matter
        cfg_path = os.path.normpath(os.path.join(
            os.path.dirname(__file__), '..', 'infrastructure', 'rules', 'language_rules', 'common', 'normalization.yml'
        ))

        if os.path.exists(cfg_path):
            with open(cfg_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}
        else:
            data = {}

        lowercase = data.get("lowercase", True)
        trim_spaces = data.get("trim_spaces", True)
        normalize_quotes = data.get("normalize_quotes", True)
        normalize_dashes = data.get("normalize_dashes", True)

        return NormalizerRules(lowercase, trim_spaces, normalize_quotes, normalize_dashes)

    def _normalize_exact(self, text):
        if self.normalizer_rules.lowercase:
            text = text.lower()
        if self.normalizer_rules.trim_spaces:
            text = ' '.join(text.split())
        if self.normalizer_rules.normalize_quotes:
            text.replace("\'","\"")
        if self.normalizer_rules.normalize_dashes:
            text.replace("–","-")
            text.replace("—","-")
        return text

    def _normalize_fuzzy(self, text):
        text = self._normalize_exact(text)
        #also remove punctuation
        text = ''.join([char for char in text if char not in string.punctuation])
        return text