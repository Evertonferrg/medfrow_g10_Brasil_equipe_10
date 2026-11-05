#!/bin/bash
# GitOps do MediFlow: roda como opc, chamado pelo mediflow-sync.timer (a cada ~2 min).
# Só implanta um commit da main quando a CI já publicou a imagem com a tag = SHA desse commit.
set -euo pipefail

REPO=$HOME/mediflow
ESTADO=$HOME/.mediflow-implantado
QUADLET_DIR=$HOME/.config/containers/systemd
CONF_DIR=$HOME/.config/mediflow

cd "$REPO"
git fetch -q origin main
SHA=$(git rev-parse origin/main)
[ "$SHA" = "$(cat "$ESTADO" 2>/dev/null || true)" ] && exit 0

# O nome da imagem sai do próprio modelo na main (o namespace fica escrito num lugar só).
IMAGE=$(git show origin/main:deploy/quadlet/mediflow.container | sed -n 's/^Image=\(.*\):__TAG__$/\1/p')
if [ -z "$IMAGE" ]; then
  echo "ERRO: linha Image=...:__TAG__ não encontrada em deploy/quadlet/mediflow.container" >&2
  exit 1
fi

if ! podman pull -q "$IMAGE:$SHA" >/dev/null 2>&1; then
  echo "Imagem $SHA ainda não existe; mantendo a versão atual"
  exit 0
fi

git merge -q --ff-only origin/main
mkdir -p "$QUADLET_DIR" "$CONF_DIR"

# Copia um arquivo só se mudou; devolve 0 quando mudou.
instalar() {
  if cmp -s "$1" "$2"; then return 1; fi
  cp "$1" "$2"
}

CADDY_MUDOU=0
instalar deploy/Caddyfile "$CONF_DIR/Caddyfile" && CADDY_MUDOU=1
for f in deploy/quadlet/*; do
  nome=$(basename "$f")
  [ "$nome" = mediflow.container ] && continue
  if instalar "$f" "$QUADLET_DIR/$nome" && [ "$nome" = caddy.container ]; then
    CADDY_MUDOU=1
  fi
done
sed "s|__TAG__|$SHA|" deploy/quadlet/mediflow.container > "$QUADLET_DIR/mediflow.container"

systemctl --user daemon-reload
systemctl --user restart mediflow
if [ "$CADDY_MUDOU" = 1 ]; then
  systemctl --user restart caddy
else
  systemctl --user start caddy
fi

echo "$SHA" > "$ESTADO"
echo "Implantado $SHA"
