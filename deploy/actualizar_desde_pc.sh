#!/bin/sh
# Actualiza el servidor de Oracle desde el PC: copia de seguridad, código nuevo, app web nueva.
#
#   cd app && flutter build web --base-href /app/ && cd ..
#   sh deploy/actualizar_desde_pc.sh
#
# Variables opcionales: SERVIDOR (por defecto bioyologic.duckdns.org) y CLAVE (llave SSH).
# Solo actualiza backend/, deploy/, Dockerfile y la app web: los modelos que ya están en la VM no se tocan
# (en GitHub viven en Git LFS y la VM los tiene copiados a mano).
set -eu
SERVIDOR="${SERVIDOR:-bioyologic.duckdns.org}"
CLAVE="${CLAVE:-$HOME/.ssh/bioyologic_oracle}"
cd "$(dirname "$0")/.."
[ -f app/build/web/index.html ] || { echo "Falta app/build/web: compila la app web primero"; exit 1; }

echo "1/4 Copiando la app web al servidor..."
ssh -i "$CLAVE" "ubuntu@$SERVIDOR" 'rm -rf ~/web_nueva'
scp -q -i "$CLAVE" -r app/build/web "ubuntu@$SERVIDOR:~/web_nueva"

echo "2/4 Copia de seguridad, código nuevo y reconstrucción..."
ssh -i "$CLAVE" "ubuntu@$SERVIDOR" 'set -e
cd ~/bioyologic/deploy && sh backup.sh
cd ~/bioyologic
git fetch -q origin
git checkout origin/main -- backend deploy Dockerfile LICENSE
rm -rf app/build/web && mkdir -p app/build && mv ~/web_nueva app/build/web
cd deploy && docker compose up -d --build'

echo "3/4 Comprobando..."
sleep 15
curl -fsS "https://$SERVIDOR/health"; echo
code=$(curl -s -o /dev/null -w "%{http_code}" "https://$SERVIDOR/analyses")
[ "$code" = "401" ] && echo "OK: los análisis ya piden iniciar sesión" || echo "ATENCIÓN: /analyses respondió $code (se esperaba 401)"

echo "4/4 Datos de antes de las cuentas (sin dueño):"
ssh -i "$CLAVE" "ubuntu@$SERVIDOR" 'cd ~/bioyologic/deploy && docker compose exec -T -w /srv/backend bioyologic python -m bioyologic.manage orphans'
echo "Para borrarlos:  ssh -i $CLAVE ubuntu@$SERVIDOR 'cd ~/bioyologic/deploy && docker compose exec -T -w /srv/backend bioyologic python -m bioyologic.manage delete-orphans --yes'"
