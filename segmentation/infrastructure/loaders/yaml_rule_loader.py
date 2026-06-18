import yaml
from ...domain.models.language_rules import LanguageRules
from ..constants.file_paths import LANGUAGE_RULES_PATH, ABBREVIATIONS, SEGMENTATION

class YamlRuleLoader:
    def load(self, language: str) -> LanguageRules:

        directory_abbreviations = f"{LANGUAGE_RULES_PATH}/{language}/{ABBREVIATIONS}.yml"
        directory_segmentation = f"{LANGUAGE_RULES_PATH}/{language}/{SEGMENTATION}.yml"

        with open(directory_abbreviations, 'r') as f:
            data = yaml.full_load(f)
            abbreviations = data.get(ABBREVIATIONS,[])
            abbreviations = set(abbreviations)
        with open(directory_segmentation, 'r') as f:
            data = yaml.full_load(f)
            segmentation = data.get(SEGMENTATION,[])
            segmentation = ''.join(segmentation)
#check if it works
        #return LanguageRules file
        language_rules = LanguageRules(abbreviations=abbreviations, sentence_endings=segmentation)
        return language_rules