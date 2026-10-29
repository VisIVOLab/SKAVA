# A testbed node: the VisIVO backend image (`make node-base`, built from the
# VisIVO Visual Analytics repository) plus SoFiA-2, compiled from source so the
# node can run the source finder next to its data.
ARG BASE=skava-testbed-node-base
FROM ${BASE}

# A stable release of SoFiA-2 (https://gitlab.com/SoFiA-Admin/SoFiA-2);
# the base image already carries build-essential.
ARG SOFIA_REF=v2.7.1
RUN apt-get update && apt-get install -y --no-install-recommends git wcslib-dev \
    && rm -rf /var/lib/apt/lists/* \
    && git clone --depth 1 --branch "${SOFIA_REF}" https://gitlab.com/SoFiA-Admin/SoFiA-2.git /tmp/sofia2 \
    && make -C /tmp/sofia2 OMP=true \
    && install -m 755 /tmp/sofia2/sofia /usr/local/bin/sofia2 \
    && rm -rf /tmp/sofia2

ENV VISIVO_SOFIA_BIN=/usr/local/bin/sofia2
