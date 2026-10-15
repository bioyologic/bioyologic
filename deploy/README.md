# Desplegar Bioyologic en la nube (Oracle Cloud Always Free)

Esta guía instala el servidor en una máquina virtual gratuita, con HTTPS y copias de seguridad diarias. El servidor usa los modelos ONNX, no necesita PyTorch y funciona en procesadores ARM.

```
Internet ──HTTPS──▶ Caddy (certificado de Let's Encrypt) ──▶ API Bioyologic (Docker) ──▶ ./data (SQLite + fotos)
```

## Antes de empezar (en tu PC)

```bash
.venv/Scripts/python backend/scripts/export_onnx.py      # models/*.onnx
cd app && flutter build web --base-href /app/            # app web en /app
```

El servidor descarga el proyecto con `git clone`. Los modelos `.onnx` y `.json` vienen en el repositorio (con Git LFS: `sudo apt install git-lfs && git lfs pull`). La app web (`app/build/web`) no va en git: súbela con `scp -r app/build/web ubuntu@IP:~/bioyologic/app/build/`.

## 1. Crear la máquina virtual (lo haces tú en la consola de Oracle)

1. Crea una cuenta en https://cloud.oracle.com. Pide una tarjeta solo para verificar; el plan *Always Free* no cobra.
2. Ve a *Compute → Instances → Create instance*:
   - **Imagen:** Ubuntu 24.04.
   - **Forma:** `VM.Standard.A1.Flex` (Ampere ARM). Elige 2 OCPU y 12 GB de RAM; con 1 OCPU y 6 GB también basta.
   - **Clave SSH:** sube tu clave pública o descarga la que genera Oracle.
3. En la *VCN* de la instancia, ve a *Security List → Ingress rules* y abre los puertos **80** y **443** (TCP, origen `0.0.0.0/0`).

Si aparece *Out of capacity*, prueba otro dominio de disponibilidad o vuelve a intentarlo más tarde.

## 2. Dominio gratuito

1. Entra en https://www.duckdns.org, crea un subdominio (p. ej. `bioyologic.duckdns.org`) y apúntalo a la IP pública de la VM.
2. Si prefieres otro dominio, basta con un registro DNS `A` hacia esa IP.

## 3. Instalar en la VM

```bash
ssh ubuntu@IP_PUBLICA
sudo apt update && sudo apt install -y docker.io docker-compose-v2 git
sudo usermod -aG docker $USER && newgrp docker
# Ubuntu en Oracle bloquea los puertos con iptables, además de la Security List:
sudo iptables -I INPUT 6 -p tcp -m multiport --dports 80,443 -j ACCEPT
sudo netfilter-persistent save

git clone https://github.com/bioyologic/bioyologic.git && cd bioyologic
# copia aquí models/*.onnx, models/*.json y app/build/web
cd deploy
cp .env.example .env && nano .env        # dominio y URL del código fuente
docker compose up -d --build
docker compose logs -f                    # la primera vez Caddy obtiene el certificado
```

Comprueba que funciona: `https://TU_DOMINIO/health` debe responder `{"status":"ok",...}` y la app web estará en `https://TU_DOMINIO/app/`.

## 4. Copias de seguridad

```bash
chmod +x backup.sh && ./backup.sh        # prueba manual
crontab -e                                # y añade:
30 3 * * * /home/ubuntu/bioyologic/deploy/backup.sh >> /home/ubuntu/backup.log 2>&1
```

Se guardan en `~/backups` durante 14 días. Conviene copiarlas de vez en cuando fuera de la VM.

## 5. Apuntar la app al servidor

- **Ya instalada:** *Perfil → Configuración → Servidor* → `https://TU_DOMINIO`.
- **Compilada con el servidor por defecto:**
  ```bash
  flutter build apk --release --dart-define=BIOYOLOGIC_SERVER=https://TU_DOMINIO
  ```

## Actualizar

```bash
cd ~/bioyologic && git pull && cd deploy && docker compose up -d --build
```

## Alternativa: Hugging Face Spaces (demo)

1. Crea un *Space* de tipo **Docker** y sube el `Dockerfile`, `backend/`, `models/*.onnx`, `models/*.json`, `app/build/web` y `LICENSE`.
2. Añade al principio del `README.md` del Space:
   ```yaml
   ---
   sdk: docker
   app_port: 8000
   ---
   ```
3. Ten en cuenta que el Space se duerme si no se usa y que **los análisis se pierden al reiniciarse**. Sirve como demo, no como servidor principal.

## Variables de entorno

Ver `.env.example` y la cabecera de `backend/bioyologic/api/main.py`. Las más importantes:

| Variable | Qué hace |
|---|---|
| `BIOYOLOGIC_SOURCE_URL` | Enlace al código fuente. La AGPL-3.0 obliga a ofrecerlo a quien usa el servidor; la app lo muestra en «Acerca de» |
| `BIOYOLOGIC_RATE_LIMIT` | Máximo de análisis por minuto desde una misma IP |
| `BIOYOLOGIC_MAX_UPLOAD_MB` | Tamaño máximo de cada foto |
