# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
from dataclasses import dataclass


@dataclass(frozen=True)
class CirclePos:
    ra: float
    dec: float
    radius: float


@dataclass(frozen=True)
class NumericInterval:
    min_value: float
    max_value: float

