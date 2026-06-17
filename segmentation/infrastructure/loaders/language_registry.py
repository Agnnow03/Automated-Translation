from yaml_rule_loader import YamlRuleLoader

class LanguageRegistry:
    def __init__(self, loader=YamlRuleLoader):
        self.loader = loader
        self.cache = {}

    def get(self, language):

        if language not in self.cache:
            self.cache[language] = self.loader.load(
                language
            )

        return self.cache[language]