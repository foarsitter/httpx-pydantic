from collections import defaultdict
from enum import Enum
from typing import Annotated
from typing import Any
from typing import ClassVar
from typing import Dict
from typing import Generic
from typing import Optional
from typing import Type
from typing import TypeVar

import httpx
from fastapi import Header
from fastapi import Path
from fastapi import Query
from fastapi import params
from fastapi.encoders import jsonable_encoder
from httpx import Request
from pydantic import BaseModel
from pydantic import Field
from pydantic.fields import FieldInfo


ResponseType = TypeVar("ResponseType", bound=BaseModel)


class HealthType(str, Enum):
    WORKING = "working"


class RequestModel(BaseModel, Generic[ResponseType]):
    url: ClassVar[str]
    method: ClassVar[str]

    response_model: ClassVar[Type[ResponseType]]  # type: ignore[misc]

    body: Optional[BaseModel] = None

    class Config:
        allow_population_by_field_name = True

    def as_request(self) -> Request:
        request_args: Dict[Type[FieldInfo], Dict[str, Any]] = defaultdict(dict)

        for k, v in self.__annotations__.items():
            annotated_property = v.__metadata__[0]

            request_args[type(annotated_property)][k] = getattr(self, k)

        body = jsonable_encoder(self.body) if self.body else None

        r = Request(
            method=self.method,
            url=self.url.format(**request_args[params.Path]),
            params=request_args[params.Query],
            headers=request_args[params.Header],
            cookies=request_args[params.Cookie],
            data=request_args[params.Body],
            files=request_args[params.File],
            json=body,
        )

        return r

    def send(self, client: httpx.Client) -> ResponseType:
        r = self.as_request()
        response = client.send(r)
        return self.response_model.parse_obj(response.json())

    async def asend(self, client: httpx.AsyncClient) -> ResponseType:
        r = self.as_request()
        response = await client.send(r)
        return self.response_model.parse_obj(response.json())


class HealthCheckResponse(BaseModel):
    cache_backend_default: HealthType = Field(..., alias="Cache backend: default")
    celery_health_check_celery: HealthType = Field(..., alias="CeleryHealthCheckCelery")
    database_backend: HealthType = Field(..., alias="DatabaseBackend")
    default_file_storage_health_check: HealthType = Field(
        ..., alias="DefaultFileStorageHealthCheck"
    )
    meldingen_stroom: str = Field(..., alias="Meldingen stroom")


class HealthCheckRequest(RequestModel[HealthCheckResponse]):
    url = "https://broker.amsvr.nl/{page}/"
    method = "GET"

    response_model = HealthCheckResponse

    search: Annotated[str, Query(min_length=3, max_length=10)]
    version: Annotated[str, Header(alias="X-Version")]
    accept: Annotated[str, Header(alias="Accept")] = "application/json"
    page: Annotated[str, Path()]


if __name__ == "__main__":
    p = HealthCheckRequest(search="xyz", version="v1", page="health")

    request = p.as_request()

    assert request.url == "https://broker.amsvr.nl/health/?search=xyz", request.url

    with httpx.Client() as c:
        health = p.send(c)

    assert health.celery_health_check_celery == HealthType.WORKING
    assert health.database_backend == HealthType.WORKING
