# Minimal Sphinx Makefile mirroring the one ``sphinx-quickstart`` ships
# with — kept hand-written so we know exactly what's in it.

SPHINXOPTS    ?= -W --keep-going -n
SPHINXBUILD   ?= sphinx-build
SOURCEDIR      = .
BUILDDIR       = _build

.PHONY: help html clean livehtml linkcheck

help:
	@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS)

html:
	@$(SPHINXBUILD) -b html "$(SOURCEDIR)" "$(BUILDDIR)/html" $(SPHINXOPTS)
	@echo
	@echo "Open file://$(PWD)/$(BUILDDIR)/html/index.html"

# Live reload during writing — needs ``pip install sphinx-autobuild``.
livehtml:
	sphinx-autobuild "$(SOURCEDIR)" "$(BUILDDIR)/html" --open-browser $(SPHINXOPTS)

# Catch dead links before publishing.
linkcheck:
	@$(SPHINXBUILD) -b linkcheck "$(SOURCEDIR)" "$(BUILDDIR)/linkcheck" $(SPHINXOPTS)

clean:
	rm -rf "$(BUILDDIR)"
