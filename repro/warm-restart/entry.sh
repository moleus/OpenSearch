#!/bin/bash
set -e
cd /usr/share/opensearch
[ -f config/opensearch.keystore ] || bin/opensearch-keystore create
printf minioadmin | bin/opensearch-keystore add --stdin -f s3.client.default.access_key
printf minioadmin | bin/opensearch-keystore add --stdin -f s3.client.default.secret_key
exec ./opensearch-docker-entrypoint.sh opensearch
