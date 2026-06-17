import yaml
from domain.models.normalizer_rules import NormalizerRules
import string

class Normalizer:

    def normalize(
        self,
        text: str,
        profile: str = "exact"
    ) -> str:

        self.normalize_rules = self.load_normalizer_configuration()

        if profile == "exact":
            return self._normalize_exact(text)

        if profile == "fuzzy":
            return self._normalize_fuzzy(text)

        raise ValueError(
            f"Unknown profile: {profile}"
        )

    def load_normalizer_configuration() -> NormalizerRules:
        directory=""
        with open(directory, 'r') as f:
            data = yaml.load_all(f)
            lowercase = data.get("lowercase")
            trim_spaces = data.get("trim_spaces")
            normalize_quotes = data.get("normalize_quotes")
            normalize_dashes = data.get("normalize_dashes")

        return NormalizerRules(lowercase,trim_spaces,normalize_quotes,normalize_dashes)
        

    def _normalize_exact(self, text):
        if self.normalizer_rules.lowercase:
            text = text.lower()
        if self.normalizer_rules.trim_spaces:
            text = ' '.join(text.split())
        if self.normalize_rules.normalize_qoutes:
            text.replace("\'","\"")
        if self.normalize_rules.normalize_dashes:
            text.replace("–","-")
            text.replace("—","-")
        return text

    def _normalize_fuzzy(self, text):
        text = self._normalize_exact(text)
        #also remove punctuation
        text = ''.join([char for char in text if char not in string.punctuation])
        return text