import srt
import re

class SRTUtils:
    @staticmethod
    def time_to_sec(t):
        h, m, s_ms = t.split(":")
        s, ms = s_ms.split(",")
        return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000

    @staticmethod
    def get_subs_in_range(subs, start_t, end_t):
        start_sec = SRTUtils.time_to_sec(start_t)
        end_sec = SRTUtils.time_to_sec(end_t)
        return " ".join(
            s.content.replace('\n', ' ') for s in subs
            if s.end.total_seconds() > start_sec and s.start.total_seconds() < end_sec
        )