FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src

ENV PYTHONPATH=/app/src
RUN mkdir -p /app/outputs /app/data/pdf_cache

# Mount the OpenReview DB at runtime:
#   docker run -v /path/to/gen_review.db:/app/data/gen_review.db ...
# Or set DB_PATH env var to point to an external location.
CMD ["python", "-m", "reviewer_sim.run"]
