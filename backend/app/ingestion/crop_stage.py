from dataclasses import dataclass
from datetime import date

from app.engine import kb


@dataclass
class CropStage:
    key: str
    label: str
    day: int  # days since sowing / transplanting
    days_to_harvest_window: int  # 0 once the window has opened
    in_harvest_window: bool
    nitrogen_window: bool  # stage where N top-dressing is normally responsive


def crop_stage(crop_key: str, sowing_date: date, today: date) -> CropStage:
    crop = kb.crop(crop_key)
    day = max((today - sowing_date).days, 0)
    stages = crop["stages"]
    # past the calendar: keep reporting the last stage rather than nothing
    stage = next((s for s in stages if s["start"] <= day <= s["end"]), stages[-1])
    window_start, window_end = crop["harvest_window"]
    return CropStage(
        key=stage["key"],
        label=stage["label"],
        day=day,
        days_to_harvest_window=max(window_start - day, 0),
        in_harvest_window=window_start <= day <= window_end,
        nitrogen_window=stage["key"] in crop["nitrogen_stages"],
    )
