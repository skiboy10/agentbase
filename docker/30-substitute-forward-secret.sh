#!/bin/sh
# Substitute @@INTERNAL_FORWARD_SECRET@@ in the nginx config at container
# start. We use a custom placeholder (not envsubst) because nginx.conf
# contains nginx variables like $http_host / $scheme that envsubst would
# incorrectly expand to empty strings. See #49 for context.
set -e

if [ -n "${INTERNAL_FORWARD_SECRET}" ]; then
    # Restrict secret to safe characters so the sed substitution below
    # is robust against delimiters and metacharacters. openssl rand -hex
    # produces output in this character class.
    case "$INTERNAL_FORWARD_SECRET" in
        *[!a-zA-Z0-9_-]*)
            echo "ERROR: INTERNAL_FORWARD_SECRET contains characters outside [a-zA-Z0-9_-]." >&2
            echo "Generate with: openssl rand -hex 32" >&2
            exit 1
            ;;
    esac
    sed -i "s|@@INTERNAL_FORWARD_SECRET@@|${INTERNAL_FORWARD_SECRET}|g" \
        /etc/nginx/conf.d/default.conf
else
    # Strip the proxy_set_header lines entirely so nginx doesn't pass a
    # literal "@@INTERNAL_FORWARD_SECRET@@" string to the backend. Backend
    # middleware then sees no secret header and skips XFF rewriting,
    # which is the safe default for local dev.
    sed -i '/X-Internal-Forward-Secret/d' \
        /etc/nginx/conf.d/default.conf
    echo "INTERNAL_FORWARD_SECRET unset — backend will ignore X-Forwarded-* headers" >&2
fi
