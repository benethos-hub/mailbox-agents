#!/bin/sh
# Makes the live setup anew: a test CA and a certificate for the mail
# server, Stalwart with one account made for the agents, the mailbox
# service with an administrator, the account connected, a user for the
# agents with mail.read and mail.write on it, its token, and invented mail.
#
# Needs Docker with compose, openssl and python3. Run from the repository:
#   sh containers/live/setup.sh
#
# It removes the volumes of an earlier run. What it makes stays in
# containers/live/secrets/, never versioned: the CA, the passwords, the
# token, and secrets/agent.env, the settings the agents and smoke.py read.

set -eu

here=$(cd "$(dirname "$0")" && pwd)
secrets="$here/secrets"
compose="docker compose -f $here/compose.yaml"

say() { printf 'setup: %s\n' "$1" >&2; }

say "removing an earlier run"
$compose down --volumes --remove-orphans >/dev/null 2>&1 || true
rm -rf "$secrets"
mkdir -p "$secrets/tls"

say "a test CA and a certificate for mail.agents.test"
openssl req -x509 -newkey rsa:2048 -nodes -days 3650 -subj "/CN=mailbox-agent live test CA" \
    -keyout "$secrets/tls/ca.key" -out "$secrets/tls/ca.pem" 2>/dev/null
openssl req -newkey rsa:2048 -nodes -subj "/CN=mail.agents.test" \
    -keyout "$secrets/tls/server.key" -out "$secrets/tls/server.csr" 2>/dev/null
printf 'subjectAltName=DNS:mail.agents.test,DNS:localhost,IP:127.0.0.1\n' > "$secrets/tls/san.ext"
openssl x509 -req -in "$secrets/tls/server.csr" -CA "$secrets/tls/ca.pem" \
    -CAkey "$secrets/tls/ca.key" -CAcreateserial -days 3650 \
    -extfile "$secrets/tls/san.ext" -out "$secrets/tls/server.pem" 2>/dev/null
chmod 644 "$secrets/tls/ca.pem"

say "passwords"
rand() { openssl rand -hex 16; }
stalwart_admin=$(rand)
mailbox_password=$(rand)
service_password="$(rand)Aa1!"

say "the master key of the mailbox service"
$compose run --rm --no-deps -T mailbox-service keys generate > "$secrets/master_key"
# The container's user reads it. A test key, so readable rather than owned.
chmod 444 "$secrets/master_key"
$compose run --rm --no-deps -T mailbox-service keys init > /dev/null
one_time=$($compose run --rm --no-deps -T mailbox-service users create-admin 2>/dev/null)

say "Stalwart in bootstrap mode"
STALWART_RECOVERY_ADMIN="admin:$stalwart_admin" $compose up -d stalwart >/dev/null 2>&1

say "the mailbox service"
$compose up -d mailbox-service >/dev/null 2>&1

say "provisioning"
STALWART_URL=http://127.0.0.1:38080 \
STALWART_BOOTSTRAP_PASSWORD="$stalwart_admin" \
MAILBOX_PASSWORD="$mailbox_password" \
SERVICE_URL=http://127.0.0.1:38081 \
SERVICE_ONE_TIME_PASSWORD="$one_time" \
SERVICE_PASSWORD="$service_password" \
SECRETS="$secrets" \
COMPOSE="$compose" \
    python3 "$here/provision.py"

say "done: containers/live/secrets/agent.env holds the settings for the agents"
