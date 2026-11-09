# Both variants use the released 3.9.0 image and repository-s3 plugin.
FROM eclipse-temurin:21-jdk-jammy AS source
RUN apt-get update && apt-get install -y --no-install-recommends git unzip ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /src
RUN git init && git remote add origin https://github.com/opensearch-project/OpenSearch.git && git fetch --depth=1 origin 4ee42a94e87f66fbf1e62a9871b1b87f91e02472 && git checkout --detach FETCH_HEAD

FROM source AS builder
COPY fix.patch /tmp/fix.patch
RUN git apply --check /tmp/fix.patch && git apply /tmp/fix.patch && ./gradlew :server:jar -Dbuild.snapshot=false -Dorg.gradle.jvmargs=-Xmx4g -Dorg.gradle.workers.max=4 --console=plain

FROM opensearchproject/opensearch:3.9.0 AS stock
RUN /usr/share/opensearch/bin/opensearch-plugin install --batch repository-s3
RUN if [ ! -f config/opensearch.keystore ]; then bin/opensearch-keystore create; fi
RUN printf minioadmin | bin/opensearch-keystore add --stdin -f s3.client.default.access_key && printf minioadmin | bin/opensearch-keystore add --stdin -f s3.client.default.secret_key

FROM stock AS fixed
LABEL org.opencontainers.image.source="https://github.com/moleus/OpenSearch" \
      org.opencontainers.image.description="OpenSearch 3.9.0 with the production-code diff from PR 23563 at 5d346deda1ec71d8293ea5faa0ed722c8a83e39f"
COPY --from=builder --chown=opensearch:opensearch /src/server/build/distributions/opensearch-3.9.0.jar /usr/share/opensearch/lib/opensearch-3.9.0.jar
