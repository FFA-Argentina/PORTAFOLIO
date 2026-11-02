# Tablero CEDEAR

Ranking de CEDEARs y acciones del panel general de BYMA, carteras óptimas (media-varianza, paridad de riesgo, media-CVaR, GJR-GARCH, regímenes HMM), validación fuera de muestra y seguimiento de carteras propias en pesos o en dólares.

Todo se calcula en el navegador a partir de `data/ced.js` y `data/ar.js`. La página funciona en computadoras, iPhone y Android, y se puede instalar como aplicación.

## Publicarlo en GitHub Pages

1. Creá un repositorio nuevo en GitHub (público, para usar Pages gratis).
2. Subí el contenido de esta carpeta: **Add file → Upload files** y arrastrá todo, incluida la carpeta oculta `.github` (en Mac, mostrá los archivos ocultos con Cmd + Shift + punto). Con git: `git init && git add . && git commit -m "Tablero" && git branch -M main && git remote add origin URL && git push -u origin main`.
3. **Settings → Pages → Build and deployment → Source: GitHub Actions.**
4. **Settings → Actions → General → Workflow permissions: Read and write permissions.**
5. En **Actions**, abrí "Actualizar datos y publicar" y tocá **Run workflow** (modo `full`) para probar. Al terminar, la página queda en `https://TU-USUARIO.github.io/NOMBRE-DEL-REPO/`.

## Actualización automática

El archivo `.github/workflows/actualizar.yml` corre `pipeline.py` en días hábiles:

- cada hora de 11:45 a 18:45 (Buenos Aires), con los precios del momento;
- a las 20:15, con la reconstrucción completa sobre los cierres oficiales.

Después de cada corrida guarda los datos en el repositorio y vuelve a publicar la página. GitHub puede demorar unos minutos las tareas programadas, y las suspende si el repositorio pasa 60 días sin actividad (se reactivan desde la pestaña Actions). Las fuentes son data912.com y Yahoo Finance; si Yahoo limita las consultas desde los servidores de GitHub, la corrida falla y los datos quedan como estaban hasta la siguiente.

## En el celular

- **iPhone o iPad:** abrí la dirección en Safari → Compartir → **Agregar a inicio**.
- **Android:** abrí la dirección en Chrome → menú ⋮ → **Instalar aplicación** (o "Agregar a la pantalla principal").

Una vez instalada se abre a pantalla completa y, sin conexión, muestra la última versión que vio.

## Carteras propias

Las carteras de la pestaña "Mi cartera" se guardan en cada navegador. Para pasarlas de un dispositivo a otro, usá **Exportar** e **Importar** al pie de esa pestaña.

## Archivos

| Archivo | Qué es |
|---|---|
| `index.html` | La página |
| `data/ced.js`, `data/ar.js` | Datos de CEDEARs y acciones argentinas (series en USD, CCL diario) |
| `pipeline.py` | Proceso de datos: `python pipeline.py intraday --out .` o `python pipeline.py full --out . --prev .` |
| `vendor/chart.umd.min.js` | Biblioteca de gráficos (Chart.js 4.4.1), local para funcionar sin conexión |
| `manifest.webmanifest`, `sw.js`, `icons/` | Instalación como aplicación y uso sin conexión |
| `.github/workflows/actualizar.yml` | Actualización programada y publicación en Pages |

Herramienta analítica; no constituye asesoramiento financiero.
