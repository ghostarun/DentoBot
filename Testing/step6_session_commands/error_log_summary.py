# Slicer error-log contents as the operator's red/yellow status-bar icon sees them
# (operator 2026-10-03: no error entries unless a step fails). Read only.
import collections

import slicer

model = slicer.app.errorLogModel()
# ctkErrorLogAbstractModel::ColumnsIds (Time, ThreadId, LogLevel, Origin,
# Description). PythonQt exposes neither the enum nor that accessor, so read
# the cells through the Qt item-model API.
level_column, origin_column = 2, 3


def _cell(row, column):
    return str(model.data(model.index(row, column)))


levels = collections.Counter()
groups = collections.Counter()
for row in range(int(model.logEntryCount())):
    level = _cell(row, level_column)
    levels[level] += 1
    if level in ("Info", "Debug", "Trace", "Status"):
        continue
    origin = _cell(row, origin_column)
    text = " ".join(str(model.logEntryDescription(row)).split())[:160]
    groups[(level, origin, text)] += 1
result = {
    "errors": sum(levels[name] for name in ("Error", "Critical", "Fatal")),
    "warnings": int(levels["Warning"]),
    "levels": dict(levels),
    "entries": [{"level": level, "origin": origin, "count": count, "text": text}
                for (level, origin, text), count in groups.most_common(40)],
}
