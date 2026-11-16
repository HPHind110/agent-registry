"""Demo invocation v1. Business schemas never enter Registry backend."""
from typing import Any
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, str_strip_whitespace=True)


class Invocation(StrictModel):
    capability: str = Field(min_length=1, max_length=100)
    input: dict[str, Any]


class InvocationResult(StrictModel):
    agent_id: str
    capability: str
    output: dict[str, Any]


class WeatherInput(StrictModel):
    city: str = Field(default='Hanoi', min_length=1, max_length=100)


class SearchInput(StrictModel):
    keyword: str = Field(min_length=1, max_length=100)


class SummaryInput(StrictModel):
    text: str = Field(min_length=1, max_length=10000)


class WeatherOutput(StrictModel):
    city: str = Field(min_length=1)
    temperature_c: float = Field(allow_inf_nan=False)
    condition: str = Field(min_length=1)
    source: str = Field(min_length=1)


class Article(StrictModel):
    title: str
    summary: str


class SearchOutput(StrictModel):
    articles: list[Article]


class SummaryOutput(StrictModel):
    summary: str = Field(min_length=1)


def validated_input(schema, data):
    try:
        return schema.model_validate(data)
    except ValidationError as exc:
        raise HTTPException(422, detail={'code': 'invalid_input',
                            'errors': exc.errors(include_context=False, include_input=False)}) from None
