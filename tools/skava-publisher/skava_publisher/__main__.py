# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
"""Allow ``python -m skava_publisher`` as a fallback to the entry-point script."""
from skava_publisher.cli import main

if __name__ == "__main__":
    main()
