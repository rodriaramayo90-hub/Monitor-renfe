# Interfaz web del Monitor Renfe

Esta carpeta contiene un Cloudflare Worker que sirve el formulario móvil y actualiza `config.json` de forma segura.

## Secrets necesarios en Cloudflare
- `GITHUB_TOKEN`: token fine-grained de GitHub con acceso solo a este repositorio y permiso **Contents: Read and write**.
- `APP_PIN`: PIN privado que deberá introducir el usuario del formulario.

Nunca escribas estos valores en el repositorio.

## Despliegue
Desde Cloudflare Workers & Pages se puede crear/importar un Worker desde este repositorio, usando:
- Root directory: `webapp`
- Wrangler config: `webapp/wrangler.toml`

Después añade los dos secrets anteriores en Settings > Variables and Secrets y despliega.

El formulario permite seleccionar trayecto, fecha mediante calendario, franja horaria, pasajeros, activar y desactivar el monitor.
