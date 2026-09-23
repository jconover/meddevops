FROM public.ecr.aws/lambda/python:3.14
COPY --from=ghcr.io/astral-sh/uv:0.12.17 /uv /bin/uv

WORKDIR /build
COPY . .
RUN uv export --frozen --no-dev --no-editable --no-hashes --package ingest -o requirements.txt \
    && uv pip install --no-cache --no-editable --target "${LAMBDA_TASK_ROOT}" -r requirements.txt \
    && rm -rf /build

WORKDIR ${LAMBDA_TASK_ROOT}
CMD ["ingest.handler.lambda_handler"]
