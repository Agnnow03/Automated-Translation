class Segmenter:
    def __init__(
        self,
        rules,
        context_builder
    ):
        self.rules = rules
        self.context_builder = context_builder

    def segment(self, text):

        segments = self._split(text)

        return self.context_builder.build(#to get prev,next sentences
            segments
        )
    
    def _split(
        self,
        text: str
    ) -> list[str]:

        segments = []

        start_index = 0
        end_index = 0
        current = ""

        for i in range (len(text)):
            current+= text[i]

            if text[i] in self.rules.sentence_endings:
                if self._prevent_break(current):
                    continue
            
                end_index = i
                segments.append([current,start_index,end_index])
                
                start_index = i
                end_index = 0
                current = ""

        return segments

    
    def _prevent_break(
        self,
        text: str
    ) -> bool:

        last_token = (
            text.split()[-1]
            if text.split()
            else ""
        )

        if (
            last_token
            in self.rules.abbreviations
        ):
            return True

        
        return False