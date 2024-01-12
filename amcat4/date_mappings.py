from inspect import isclass
from typing import Optional, Iterable


class DateMapping:
    interval = None

    def mapping(self, field: str) -> dict:
        return {self.fieldname(field): {"type": self.mapping_type(), "script": self.mapping_script(field)}}

    def mapping_script(self, field: str) -> str:
        raise NotImplementedError()

    def mapping_type(self):
        return "keyword"

    def fieldname(self, field: str) -> str:
        return f"{field}_{self.interval}"

    def postprocess(self, value):
        return value


class DayOfWeek(DateMapping):
    interval = "dayofweek"

    def mapping_script(self, field):
        return f"emit(doc['{field}'].value.dayOfWeekEnum.getDisplayName(TextStyle.FULL, Locale.ROOT))"


class DayPart(DateMapping):
    interval = "daypart"

    def mapping_script(self, field):
        return """
            int hour =doc['date'].value.hour;
            if (hour < 6) emit('Night');
            else if (hour < 12) emit('Morning');
            else if (hour < 18) emit('Afternoon');
            else emit('Evening')
        """


class MonthName(DateMapping):
    interval = "monthnr"

    def mapping_type(self):
        return "double"

    def mapping_script(self, field):
        return "emit(doc['date'].value.getMonthValue())"

    def postprocess(self, value):
        return int(value)


class YearNr(DateMapping):
    interval = "yearnr"

    def mapping_type(self):
        return "double"

    def mapping_script(self, field):
        return "emit(doc['date'].value.getYear())"

    def postprocess(self, value):
        return int(value)


class DayOfMonth(DateMapping):
    interval = "dayofmonth"

    def mapping_type(self):
        return "double"

    def mapping_script(self, field):
        return "emit(doc['date'].value.getDayOfMonth())"

    def postprocess(self, value):
        return int(value)


class Weeknr(DateMapping):
    interval = "weeknr"

    def mapping_type(self):
        return "double"

    def mapping_script(self, field):
        return "emit(doc['date'].value.get(IsoFields.WEEK_OF_WEEK_BASED_YEAR))"

    def postprocess(self, value):
        return int(value)


def interval_mapping(interval: str | None) -> Optional[DateMapping]:
    if interval is not None:
        for m in mappings():
            if m.interval == interval:
                return m
    return None


def mappings() -> Iterable[DateMapping]:
    for c in globals().values():
        if isclass(c) and issubclass(c, DateMapping) and c != DateMapping and c.interval is not None:
            yield c()
