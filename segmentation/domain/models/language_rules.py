class LanguageRules:
    def __init__(
        self,
        abbreviations: set[str],
        sentence_endings: str = ".!?"
    ):
        self.abbreviations = abbreviations
        self.sentence_endings = sentence_endings