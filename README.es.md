# Mubu Exporter

[简体中文](README.md) · [English](README.en.md) · **Español** · [日本語](README.ja.md)

Convierte esquemas de Mubu en Markdown portátil. Conserva carpetas, texto enriquecido, estados de tareas, tablas, fórmulas y referencias entre documentos, con la opción de descargar las imágenes.

Python 3.10+ · Windows / Linux · [MIT](LICENSE)

## Probar el ejemplo

El caso sintético incluido se puede convertir sin cuenta ni token de Mubu y sin conexión durante la conversión. Ejecuta los comandos desde la raíz del repositorio:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install .
mubu-export inspect --cache examples/cache
mubu-export export --cache examples/cache --out exports/demo --images skip
```

En Linux o macOS, activa el entorno con `source .venv/bin/activate`. Abre `exports/demo/index.md` para explorar los archivos exportados. El directorio de salida debe ser nuevo; elige otro nombre para cada ejecución.

Consulta la [caché de ejemplo](examples/cache) y la [vista previa de la exportación](examples/preview/index.md) para ver la entrada y el resultado real. Ambas contienen solo material ficticio.

## Qué se conserva

| Contenido | Representación en Markdown |
| --- | --- |
| Carpetas y documentos con el mismo nombre | Rutas estables y únicas según el ID, evitando nombres reservados de Windows y colisiones entre mayúsculas y minúsculas |
| Esquemas | Encabezados de nivel adaptable o listas completamente anidadas |
| Negrita, cursiva, tachado y código en línea | Sintaxis de Markdown; se conservan los acentos graves y los espacios del código |
| Resaltado y texto para completar | `==resaltado==` y `{{hueco}}`; la visualización depende del lector |
| Subrayado y colores | Una pequeña cantidad de HTML; `--no-color` omite los colores |
| Fórmulas | `$LaTeX$`; el lector debe admitir fórmulas |
| Tareas y notas | `- [ ]` / `- [x]` y citas en bloque |
| Tablas simples | Tablas GFM que conservan el texto escapado y los saltos de línea dentro de las celdas |
| Referencias a documentos | Enlaces relativos y anclas de nodo para los documentos exportados; enlaces de Mubu para los que quedan fuera |
| Imágenes | Conservar las URL remotas, descargar las imágenes u omitirlas de forma explícita |

Las celdas combinadas, las tablas anidadas y los datos que se sabe que están incompletos provocan un error explícito para evitar exportaciones aparentemente exitosas que pierdan contenido. El esquema no reproduce la interfaz interactiva de Mubu.

## Hacer una copia de tus documentos de Mubu

`fetch` usa la API de la interfaz web de Mubu. La herramienta no es oficial y la API puede cambiar. Úsala solo con contenido al que tengas permiso para acceder.

1. Inicia sesión en Mubu desde el navegador y abre el panel de red de las herramientas de desarrollo.
2. Selecciona una petición de documento a `api2.mubu.com` y busca la cabecera `Jwt-Token`.
3. Ejecuta el comando con entrada oculta y pega el valor. El token se usa solo en ese proceso y no se guarda en ningún archivo.

```powershell
mubu-export fetch --cache cache/backup-001 --prompt-token
mubu-export inspect --cache cache/backup-001
mubu-export export --cache cache/backup-001 --out exports/backup-001 --images local
```

Si la API necesita `data-unique-id`, define `MUBU_UNIQUE_ID`. En automatizaciones, el token se puede leer de `MUBU_TOKEN`. No lo incluyas en scripts, argumentos de comandos, capturas ni Git.

La copia pagina los documentos, incorpora las notas diarias y vuelve a obtener todos los documentos. La existencia de archivos antiguos no impide actualizarlos. Un fallo de la API de notas diarias detiene la copia; añade `--no-daily` si deseas excluir esas notas.

Las descargas y las exportaciones se preparan en un directorio temporal de la misma unidad. El directorio nuevo se publica localmente solo cuando se completan todas las comprobaciones. Los directorios existentes no se sobrescriben. La conversión solo lee documentos enumerados en `tree.json`, por lo que no incorpora archivos obsoletos.

## Opciones frecuentes

```powershell
# Convertir una caché local sin peticiones de red
mubu-export export --cache cache/backup-001 --out exports/text --images skip --no-color

# Usar listas completamente anidadas
mubu-export export --cache cache/backup-001 --out exports/bullets --style bullets

# Incluir los ID de origen y las URL de Mubu en el front matter
mubu-export export --cache cache/backup-001 --out exports/with-source --source-metadata
```

El resumen muestra solo recuentos por defecto, sin cuentas, nombres de documentos ni ID. Los ID y las URL de origen no se incluyen en el front matter a menos que se soliciten. El texto, los nombres de archivo, las anclas, los enlaces originales y las imágenes pueden contener información privada. No subas exportaciones privadas a repositorios públicos.

Las peticiones de imágenes no llevan el token de Mubu. Por defecto, solo se permiten direcciones públicas HTTPS y se rechazan redirecciones, direcciones de redes privadas, respuestas vacías, respuestas que no sean imágenes y archivos de más de 32 MiB. Para una fuente local de confianza, `--allow-private-images` permite HTTP y direcciones de redes privadas. La descarga contacta con el servidor de cada URL, que puede ser externo.

Por defecto se validan los esquemas de los enlaces y los valores de color; los valores inseguros producen un error. `--trusted-input` relaja ambas comprobaciones para datos de confianza y no se recomienda con cachés de origen desconocido. `--no-color` omite el color y conserva el texto.

## Formato de la caché local

```text
cache/backup-001/
  tree.json          # listas folders y documents, con el ID del documento como clave
  docs/<id>.json     # {"meta": {...}, "data": {"definition": ..., "directory": [...]}}
  manifest.json      # versión del esquema y número de documentos de la copia nueva
```

`definition` puede ser un objeto JSON o una cadena que contenga JSON y debe incluir la lista `nodes`. Una nota vacía válida usa `{"nodes": []}`. Los ID solo admiten letras, números, guiones bajos y guiones. El límite es de 64 niveles de nodos y 32 de carpetas. Se admiten cachés existentes con este formato; mantén las cachés privadas fuera del repositorio de código.

Una exportación contiene `index.md`, las notas individuales y `manifest.json`. El manifiesto registra el número de documentos, el modo de imágenes, las rutas de los archivos y las sumas SHA-256 para facilitar su comprobación y migración.

## Desarrollo y verificación

```powershell
python -m pip install ".[dev]"
python -m pytest
python -m ruff check .
python -m build
```

Las pruebas usan datos sintéticos e incluyen peticiones reales a un servidor HTTP local; no requieren una cuenta de Mubu. La integración continua ejecuta pruebas, análisis estático, compilación del paquete y conversión del ejemplo tras la instalación en Windows y Linux, con Python 3.10 y 3.12. La API activa de Mubu queda fuera de la integración continua pública; las pruebas sin conexión no garantizan su compatibilidad.

## Privacidad y límites

El repositorio no contiene datos de inicio de sesión, información de cuentas, notas reales, diagnósticos privados ni capturas personales. Los ejemplos y las pruebas son sintéticos y se han preparado a mano. Protege el acceso a los tokens y a las copias; consulta las [notas de privacidad](PRIVACY.md).

La herramienta no garantiza la estabilidad de la API, no elude permisos y no envía las notas a servicios de IA o de análisis. La compatibilidad con fórmulas, resaltados, texto para completar y HTML depende del lector Markdown. Los archivos adjuntos, las páginas incrustadas y otros elementos no indicados pueden no convertirse. Coteja las exportaciones importantes con el original antes de publicarlas.
