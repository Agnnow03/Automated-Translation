from segmentation.application.segmentation_service import SegmentationService
from constants.language_names import ENGLISH, POLISH

service = SegmentationService()

try:

    segments = service.segment(
        text="""
        Dr. Smith inspected the valve.
        Open the valve.
        Wait for stabilization.
        """,
        language=ENGLISH
    )
    for x in segments:
        print(x.id)
except Exception as e:
    print(e)#most likely - thsi language isnot handled