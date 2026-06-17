from yaml_rule_loader import YamlRuleLoader

class LanguageRegistry:
    instance = None

    def __new__(cls):
        if cls.instance is None:
            cls.instance = super().__new__(cls)
        return cls.instance
    
    def __init__(self, loader=YamlRuleLoader()):
        self.loader = loader
        self.cache = {}

    def get(self, language):
        if language not in self.cache:
            self.cache[language] = self.loader.load(
                language
            )

        return self.cache[language]