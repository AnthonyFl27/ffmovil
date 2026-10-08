# ffmovil

Web de recargas de diamantes de Free Fire con cuentas prepago. Backend FastAPI; PostgreSQL externo; integra la API de VentasFF.

## Documentación

El desarrollo sigue un proceso guiado por especificación (SDD):

- [`sdd/spec.md`](sdd/spec.md) — qué y por qué (fuente de verdad).
- [`sdd/plan.md`](sdd/plan.md) — arquitectura y diseño.
- [`sdd/tasks.md`](sdd/tasks.md) — tareas de implementación.
- [`sdd/changelog.md`](sdd/changelog.md) — historial de cambios de la spec.
- [`AGENTS.md`](AGENTS.md) — reglas para colaborar (humanos y LLM).

## Requisitos

- [uv](https://docs.astral.sh/uv/) (gestiona Python 3.12 y dependencias).
- Docker y Docker Compose.
- Acceso a un servidor PostgreSQL 18 (no se incluye en el Compose).

## Configuración

Copia `.env.example` a `.env` y completa los valores. El archivo `.env` nunca se sube al repositorio.

## Seguridad

Repositorio público: no se incluyen secretos, precios de costo reales, datos ni respaldos.
