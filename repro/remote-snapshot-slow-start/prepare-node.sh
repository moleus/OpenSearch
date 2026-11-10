#!/bin/sh
set -eu
cd /usr/share/opensearch
# Persist the release plugin across container recreation for both variants.
if [ ! -d plugins/repository-s3 ]; then
    bin/opensearch-plugin install --batch repository-s3
fi
if [ ! -f config/opensearch.keystore ]; then
    bin/opensearch-keystore create
fi
printf minioadmin | bin/opensearch-keystore add --stdin -f s3.client.default.access_key
printf minioadmin | bin/opensearch-keystore add --stdin -f s3.client.default.secret_key
exec ./opensearch-docker-entrypoint.sh "$@"
