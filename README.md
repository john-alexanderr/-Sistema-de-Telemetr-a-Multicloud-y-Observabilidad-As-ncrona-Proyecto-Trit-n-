# Proyecto Tritón — Sistema de Telemetría Multicloud y Observabilidad Asíncrona

Trabajo práctico grupal. Monitor CLI (`TritonMonitor`) que consulta en paralelo las APIs de
telemetría de AWS, Azure y GCP usando `asyncio` + `httpx`, resiste fallos concurrentes de red
mediante `ExceptionGroup` capturados con `except*`, y registra todo en un pipeline de logging
JSON estructurado, no bloqueante, con rotación de 2 MB y compresión Gzip.

## Arquitectura general

El flujo atraviesa cuatro fases: **frontera** (validación CLI antes de tocar la red),
**concurrencia** (un mensajero por proveedor dentro del `TaskGroup`), **captura quirúrgica**
(`except*` por familia de errores) y **logging no bloqueante** (cola + hilo aparte).
El diagrama separa los dos caminos de cada mensajero — éxito o fallo — y muestra cómo los
fallos viajan agrupados hasta la captura sin derribar la aplicación:

```mermaid
flowchart TD
    U["Usuario (terminal)"] -->|"python src/app_operator.py AWS Azure GCP -c cluster-us-east-01"| A

    subgraph F1["Fase 1 · Frontera (argparse + sanitizer.py)"]
        A["app_operator.py<br/>argparse · choices · -q/-v excluyentes"]
        S["sanitizer.py (validadores inyectados con type=)<br/>timeout de 0.1 a 5.0 s · regex del patrón"]
        X(["exit code 2 · sin event loop · sin red"])
        A -->|"inyecta validadores"| S
        S -->|"ArgumentTypeError"| X
    end

    A -->|"orden limpia"| RUN["asyncio.run(async_main)"]
    RUN --> C["core.py · scan_all_providers"]

    subgraph F2["Fase 2 · Concurrencia (asyncio.TaskGroup)"]
        TG["asyncio.TaskGroup"]
        T1["Task-AWS · /posts/1"]
        T2["Task-Azure · /posts/2"]
        T3["Task-GCP · /posts/3"]
        CH["Caos: --chaos / TRITON_BASE_URL<br/>httpbin delay/3 · status/504 · xml · host .invalid"]
        TG --> T1
        TG --> T2
        TG --> T3
        CH -.- T1
        CH -.- T2
        CH -.- T3
    end

    C --> TG

    T1 -->|"éxito"| RES["results_list (dicts)"]
    T2 -->|"éxito"| RES
    T3 -->|"éxito"| RES

    T1 -.->|"fallo como valor (_run_provider_safely)"| EG["ExceptionGroup<br/>armado con TODOS los fallos"]
    T2 -.->|"fallo como valor"| EG
    T3 -.->|"fallo como valor"| EG

    EG -->|"propaga a async_main"| CAP
    RES -->|"logger.info (reporte nominal)"| QH

    subgraph F3["Fase 3 · Captura quirúrgica (except*)"]
        CAP["except* ProviderTimeoutError<br/>except* CorruptedPayloadError<br/>except* NetworkPeeringError<br/>+ notas forenses add_note()"]
    end

    CAP -->|"logger.error + logger.debug(exc_info=group)"| QH

    subgraph F4["Fase 4 · Logging no bloqueante (hilo aparte)"]
        QH["TritonQueueHandler · prepare() intacto<br/>(el exc_info sobrevive la cola)"]
        Q["queue.Queue (thread-safe)"]
        QL["QueueListener · hilo secundario"]
        FMT["AsyncJSONFormatter<br/>ISO 8601 UTC · árbol recursivo · NDJSON"]
        CON["Consola (stdout)"]
        RF["RotatingFileHandler · 2 MB · 3 backups"]
        GZ["gzip_namer + gzip_rotator<br/>triton_services.log.N.gz"]
        QH --> Q
        Q -->|"consume desatendido"| QL
        QL --> FMT
        FMT --> CON
        FMT --> RF
        RF -->|"rollover"| GZ
    end

    F4 --> FIN["finally (PEP 765) · listener.stop()"]

    classDef conc fill:#eaf2ff,stroke:#5b7fd4,color:#1a1a1a
    classDef exito fill:#e8f4ea,stroke:#1f9d55,color:#1a1a1a
    classDef fallo fill:#fdecea,stroke:#c0392b,color:#1a1a1a
    classDef caos fill:#fff6e5,stroke:#e8a53e,stroke-dasharray:5 3,color:#1a1a1a
    classDef logging fill:#f3eaff,stroke:#6b4fa1,color:#1a1a1a
    class RUN,C,TG conc
    class RES exito
    class X,EG,CAP fallo
    class CH caos
    class QH,Q,QL,FMT,CON,RF,GZ logging
```

## Flujo de hilos del pipeline de logging

```mermaid
flowchart LR
    subgraph HP["Hilo principal · event loop de asyncio"]
        L[logger.info / logger.error] --> QH[QueueHandler]
        QH -->|encola al instante| Q[queue.Queue thread-safe]
    end
    subgraph HS["Hilo secundario · QueueListener"]
        Q --> QL[QueueListener]
        QL --> F[AsyncJSONFormatter]
        F --> R[RotatingFileHandler 2 MB / 3 backups]
        R -->|rollover| GZ[backup .gz + borrado del plano]
    end
```

El `QueueHandler` solo deposita el evento en memoria, por lo que el event loop nunca se bloquea
por escritura de disco. El hilo del `QueueListener` formatea, escribe, rota y comprime en segundo plano.

## Estructura del proyecto

```
triton_monitor/
├── src/
│   ├── triton_telemetry/
│   │   ├── __init__.py         # API publica del paquete (__all__)
│   │   ├── exceptions.py       # Jerarquia semantica (nunca BaseException)
│   │   ├── sanitizer.py        # Validadores argparse (timeout y cluster)
│   │   ├── core.py             # Telemetria concurrente (TaskGroup + httpx)
│   │   └── logging_engine.py   # Formateador JSON recursivo + pipeline por cola
│   └── app_operator.py         # Punto de entrada CLI (except* y finally PEP 765)
├── tests/                      # Tests unitarios y de integracion
├── scripts/
│   ├── chaos_suite.py          # Suite de simulacion de caos (rol 6)
│   └── forensic_validator.py   # Validador forense del log JSON (rol 6)
├── .github/workflows/ci.yml    # Integracion continua
├── requirements.txt            # httpx>=0.27.0
└── requirements-dev.txt        # pytest y ruff
```

## Instalación

Requisito: Python 3.11 o superior (`except*` es sintaxis de 3.11+).

```bash
python -m venv .venv
source .venv/bin/activate        # en Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
```

## Uso

```bash
python src/app_operator.py AWS Azure GCP -c cluster-us-east-01 -t 3.0 [--chaos] [-m nominal|debug|emergency] [-q|-v]
```

`--quiet` (`-q`) y `--verbose` (`-v`) son opciones mutuamente excluyentes. El modo
`nominal` muestra informacion, `debug` agrega trazas DEBUG y `emergency` muestra solo
errores. Si se especifica `-q` o `-v`, esa opcion prevalece sobre el modo.

## Guía de pruebas (escenarios oficiales)

### Escenario A — Operación nominal

```bash
python src/app_operator.py AWS GCP -c cluster-us-east-01 -t 3.0
```

Las corrutinas corren en paralelo y la consola muestra las latencias reales obtenidas de JSONPlaceholder.

### Escenario B — Validación temprana fallida (frontera CLI)

```bash
python src/app_operator.py AWS GCP -c cluster-invalido-id -t 9.5
```

La aplicación no abre el event loop ni conexiones de red: `argparse` recibe el
`ArgumentTypeError` del sanitizador, imprime la ayuda y sale con código 2.

### Escenario C — Inyección de caos (tormenta de errores)

```bash
python src/app_operator.py AWS Azure GCP -c cluster-us-west-02 -t 1.5 --chaos
```

Cada tarea captura su fallo semantico y el orquestador reconstruye un `ExceptionGroup` con todos
los errores concurrentes. Asi no se pierde la evidencia de los proveedores hermanos cuando uno
falla primero. Los bloques `except*` diseccionan cada categoria, imprimen las notas forenses
agregadas con `add_note()` y el volcado JSON completo queda en `triton_services.log`.

### Suite de caos y validación forense (rol 6)

```bash
python scripts/chaos_suite.py          # fuerza las cinco categorias de fallo y valida el log
python scripts/forensic_validator.py   # inspecciona el log plano y los backups .gz por separado
```

## Tests e integración continua

Los tests son offline (no necesitan internet), salvo el de la CLI que valida el código de salida:

| Archivo | Qué valida |
|---|---|
| `tests/test_sanitizer.py` | Rango de timeout [0.1, 5.0] y regex estricta de cluster (patrón exacto de la cátedra) |
| `tests/test_exceptions.py` | Herencia desde `Exception` (nunca `BaseException`) y `add_note` |
| `tests/test_formatter.py` | Serialización recursiva del `ExceptionGroup`, notas, causa y metadatos ISO 8601 UTC |
| `tests/test_core_offline.py` | Mapeo de errores de `httpx` y preservacion de fallos concurrentes con `MockTransport` |
| `tests/test_cli_integration.py` | Aborto con código 2 ante argumentos inválidos y opciones de salida excluyentes |
| `tests/test_hard_gates.py` | Prohíbe `return/break/continue` en `finally` y `except: pass` / `BaseException` |

El CI (`.github/workflows/ci.yml`) ejecuta en cada push: linting PEP 8 con `ruff` y la suite
`pytest` sobre una matriz de Python 3.11 y 3.12.

```bash
pytest tests -v
ruff check src tests scripts
```

## Mapeo semántico de errores

| Error nativo (httpx) | Excepción semántica | Causa típica |
|---|---|---|
| `httpx.TimeoutException` | `ProviderTimeoutError` | Latencia superior al `--timeout` |
| `httpx.HTTPStatusError` | `CorruptedPayloadError` | Estatus 4xx/5xx vía `raise_for_status()` |
| `json.JSONDecodeError` | `CorruptedPayloadError` | Payload no serializable (XML en lugar de JSON) |
| `httpx.RequestError` | `NetworkPeeringError` | Caída de DNS, ruteo o conectividad física |

## Roles del equipo

| Rol | Integrante | Módulo que defiende |
|---|---|---|
| Ingeniero de Robustez de Entradas y Excepciones | JUAN RASTELLINI | `exceptions.py`, `sanitizer.py` |
| Ingeniero de Concurrencia y Telemetría Asíncrona | JUAN RASTELLINI | `core.py` |
| Ingeniero de Formateo Estructurado JSON | Rodrigo Tarqui Gutierrez | `AsyncJSONFormatter` |
| Ingeniero de Almacenamiento y Desacoplamiento No Bloqueante | Rodrigo Tarqui Gutierrez | Pipeline `QueueHandler`/`QueueListener` |
| Coordinador de Integración y Flujo CLI | JUAN RASTELLINI | `app_operator.py`, empaquetado |
| Ingeniero de Simulación de Caos y Pruebas Forenses | JUAN RASTELLINI | `scripts/chaos_suite.py`, `scripts/forensic_validator.py` |

## Hardening (hard gates)

- Ninguna captura de `BaseException` ni `except: pass`.
- Ninguna sentencia `return`/`break`/`continue` dentro de bloques `finally` (PEP 765).
- Un único `RotatingFileHandler` detrás de la cola sincronizada: jamás se abre el mismo descriptor en paralelo.
- `requirements.txt` con aislamiento de dependencias y este README con diagramas Mermaid.

---

## 🏰 La historia del Reino Tritón (GitHub Pages)

¿Querés entender todo el proyecto sin leer código? Entrá al cuento ilustrado del **Reino Tritón**:
una historia con escenas dibujadas (castillo, caballero Sanitizer, mensajeros concurrentes, palomas
de `httpx`, el Tribunal de Errores, la bandeja de informes y el libro que se rota y se comprime) que
explica cada concepto del TP con un personaje del reino.

**👉 Abrir la historia:** <https://john-alexanderr.github.io/-Sistema-de-Telemetr-a-Multicloud-y-Observabilidad-As-ncrona-Proyecto-Trit-n-/docs/>


