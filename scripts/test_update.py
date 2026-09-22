import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import update as u  # noqa

D = dt.date(2026, 9, 22)
day = lambda n: D - dt.timedelta(days=n)

# streaks: current counts through yesterday if today has no commits yet
assert u.streaks({day(1), day(2), day(3), day(10), day(11)}, D) == (3, 3)
assert u.streaks({day(0), day(1)}, D) == (2, 2)
assert u.streaks({day(5)}, D) == (0, 1)
assert u.streaks(set(), D) == (0, 0)

# model families
assert u.family("claude-opus-5-5") == "Opus" and u.family("gpt-6-astra") == "GPT (Codex)" and u.family("<synthetic>") is None

# privacy guard: blocks a leaked repo name, allows substrings inside other words
try:
    u.check_private(["built for ka-tech"], ["ka-tech"])
    raise AssertionError("leak not caught")
except SystemExit:
    pass
u.check_private(["lifelong learner"], ["life"])



# merge: same session from two machines counts once, most complete copy wins
small = {"usage": {"2026-09-20": {"Opus": [10, 1]}}, "prompts": {"2026-09-20T14": 1}}
big = {"usage": {"2026-09-20": {"Opus": [50, 5]}}, "prompts": {"2026-09-20T14": 3}}
m = u.merge({"a": small}, {"a": big, "b": small})
assert m == {"a": big, "b": small}

# summarize: only days inside the window count toward "this week"
old = {"usage": {"2026-09-01": {"Fable": [100, 10]}}, "prompts": {"2026-09-01T09": 2}}
tin, tout, sess, prompts, models, times = u.summarize({"a": big, "o": old}, "2026-09-16")
assert (tin, tout, sess, prompts, models["Opus"], models["Fable"], len(times)) == (50, 5, 1, 3, 55, 0, 5)
print("ok")
