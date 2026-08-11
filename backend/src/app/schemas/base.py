from datetime import datetime, date
from typing import Annotated

from pydantic import BaseModel, ConfigDict, PlainSerializer
from pydantic.alias_generators import to_camel


def _fmt_datetime(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


DatetimeFmt = Annotated[datetime, PlainSerializer(_fmt_datetime, return_type=str)]
DateFmt = Annotated[date, PlainSerializer(lambda d: d.strftime("%Y-%m-%d"), return_type=str)]


class CamelVO(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel,
    )
