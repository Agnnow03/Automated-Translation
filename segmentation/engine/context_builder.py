from segmentation.domain.models.segment import Segment
from .normalization import Normalizer

class ContextBuilder:

    def __init__(self, normalizer=Normalizer()):
        self.normalizer = normalizer

    def build(
        self,
        texts: list[list[str]]
    ) -> list[Segment]:

        segments = []

        for idx in range(len(texts)):

            previous_idx = (
                idx -1
                if idx > 0
                else None
            )

            next_idx = (
                idx + 1
                if idx < len(texts) -1
                else None
            )

            segment = Segment(
                id=idx,

                previous_id = previous_idx,

                next_id= next_idx,

                text= texts[idx][0],

                normalize_exact=
                    self.normalizer.normalize(
                        texts[idx][0],
                        profile="exact"
                    ),

                normalize_fuzzy=
                    self.normalizer.normalize(
                        texts[idx][0],
                        profile="fuzzy"
                    ),

                start_idx=texts[idx][1],
                end_idx = texts[idx][2],
                #get start end end index in original_tetx
            )

            segments.append(segment)

        return segments