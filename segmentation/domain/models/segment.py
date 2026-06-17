from dataclasses import dataclass
from typing import Optional

@dataclass
class Segment:
    id: int
    previous_id: Optional[int]
    next_id: Optional[int]
    original_text: str
    normalized: str
    start_idx: int
    end_idx: int

#startidx endidx - where it starts in text
#previous and next id for keeping context
#normalized for currently applied normalization - to store this somewhere
#original if we want to use different normalization
#keeping id to store less data when recalling previous or next segment