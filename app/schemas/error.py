# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
from pydantic import BaseModel


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[dict] | dict | str | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody
    request_id: str | None = None
