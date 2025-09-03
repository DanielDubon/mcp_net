FROM python:3.10-slim

WORKDIR /app
COPY . /app

RUN pip install --no-cache-dir fastmcp "mcp[cli]"

ENV PORT=8000 HOST=0.0.0.0 TRANSPORT=sse
CMD ["python", "-m", "src.mcp_trivial_http"]