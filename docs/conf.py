"""Sphinx configuration for SKAVA documentation.

Renders to HTML on ReadTheDocs via the .readthedocs.yaml at the repo
root. Local preview with ``make -C docs html`` after installing
``docs/requirements.txt``.
"""
from __future__ import annotations

import os
import sys
from datetime import date

# ── Project metadata ────────────────────────────────────────────────────────
project   = "SKAVA"
author    = "INAF / SKAVA Team"
copyright = f"{date.today().year}, {author}"
version   = "0.1"
release   = "0.1.0"

# ── Path setup ──────────────────────────────────────────────────────────────
# Add the repo root to sys.path so ``autodoc`` / ``automodule`` directives
# can import ``app.*`` for the API-doc pages.
sys.path.insert(0, os.path.abspath(".."))

# ── Sphinx extensions ───────────────────────────────────────────────────────
extensions = [
    "myst_parser",                # Markdown support (MyST)
    "sphinx.ext.autodoc",         # docstring extraction (optional pages)
    "sphinx.ext.napoleon",        # Google / NumPy docstring style
    "sphinx.ext.intersphinx",     # cross-link to Python / FastAPI docs
    "sphinx.ext.viewcode",        # source code link from API pages
    "sphinx_copybutton",          # copy-to-clipboard on code blocks
    "sphinx_design",              # admonitions, grids, tabs
]

# MyST extras — enable the most useful Markdown extensions.
myst_enable_extensions = [
    "colon_fence",      # ::: blocks (admonitions, code, etc.)
    "deflist",          # PEP 257-style definition lists
    "fieldlist",        # ":param x: …" style fields in Markdown
    "tasklist",         # GitHub-style task lists
    "linkify",          # auto-detect bare URLs
    "substitution",     # |variable| substitutions
    "attrs_inline",     # {.class}{#id} on inline elements
]
myst_heading_anchors = 3  # auto-id headers up to <h3> for permalinks

# Source files: support both .md (MyST) and .rst.
source_suffix = {".md": "markdown", ".rst": "restructuredtext"}
master_doc    = "index"
language      = "en"

# Files Sphinx should ignore.
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# Show "Edit on GitHub" link.
html_context = {
    "display_github": True,
    "github_user":    "VisIVOLab",
    "github_repo":    "SKAVA",
    "github_version": "main",
    "conf_py_path":   "/docs/",
}

# ── HTML output ─────────────────────────────────────────────────────────────
html_theme  = "furo"
html_static_path = ["_static"]
html_css_files   = ["custom.css"]
html_title       = "SKAVA documentation"

# Furo theme tuning.
html_theme_options = {
    "light_css_variables": {
        "color-brand-primary":  "#70b5e3",
        "color-brand-content":  "#3a6e8c",
    },
    "dark_css_variables": {
        "color-brand-primary":  "#9bd0f0",
        "color-brand-content":  "#bce3f7",
    },
    "sidebar_hide_name": False,
    "navigation_with_keys": True,
    "footer_icons": [
        {
            "name": "GitHub",
            "url": "https://github.com/VisIVOLab/SKAVA",
            "html": "",
            "class": "fa-brands fa-github",
        },
    ],
}

# ── Intersphinx ─────────────────────────────────────────────────────────────
intersphinx_mapping = {
    "python":   ("https://docs.python.org/3", None),
    "fastapi":  ("https://fastapi.tiangolo.com/", None),
    "sqlalchemy": ("https://docs.sqlalchemy.org/en/20/", None),
    "pydantic": ("https://docs.pydantic.dev/latest/", None),
    "alembic":  ("https://alembic.sqlalchemy.org/en/latest/", None),
}

# ── Copybutton ──────────────────────────────────────────────────────────────
copybutton_prompt_text       = r">>> |\.\.\. |\$ |# "
copybutton_prompt_is_regexp  = True
copybutton_only_copy_prompt_lines = False

# ── Autodoc defaults ────────────────────────────────────────────────────────
autodoc_default_options = {
    "members":          True,
    "undoc-members":    True,
    "show-inheritance": True,
    "exclude-members":  "model_config, model_fields",
}
napoleon_google_docstring = True
napoleon_numpy_docstring  = False
