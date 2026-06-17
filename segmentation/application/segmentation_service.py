from infrastructure.loaders.language_registry import LanguageRegistry
from constants.language_names import AVAILABLE_LANGUAGES
from engine.segmenter import Segmenter
from engine.context_builder import ContextBuilder

class SegmentationService:
    def __init__(self):
        self.language_registry = LanguageRegistry() #just keep default yaml reader
        self.context_builder  = ContextBuilder()
    def segment(self, text: str, language: str):
        if language not in AVAILABLE_LANGUAGES:
            raise Exception("Unknown language: {}".format(language))
        
        rules = self.language_registry.get(language)

        segmenter = Segmenter(language, rules, self.context_builder) #should language be passed here?

        return segmenter.segment(text)
