# skava-publisher as a one-shot container: it runs next to a node's data
# (same read-only volume) and posts metadata to SKAVA. Build context: the
# repository root.
FROM python:3.11-slim
COPY tools/skava-publisher /src/skava-publisher
RUN pip install --no-cache-dir /src/skava-publisher
ENTRYPOINT ["skava-publisher"]
