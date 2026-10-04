#!/usr/bin/env python3
"""
gen_types.py

Generates TypeScript types from:
1. FastAPI OpenAPI schema -> openapi-typescript -> packages/shared-types/src/generated/api.ts
2. Pydantic WebSocket message models -> JSON Schema -> json-schema-to-typescript -> packages/shared-types/src/generated/ws.ts
"""
import json
import os
import subprocess
import sys
from pathlib import Path


def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    backend_dir = repo_root / "backend"
    shared_types_dir = repo_root / "packages" / "shared-types"
    generated_dir = shared_types_dir / "src" / "generated"
    generated_dir.mkdir(parents=True, exist_ok=True)

    # Ensure backend and backend/src are importable
    sys.path.insert(0, str(backend_dir / "src"))
    sys.path.insert(0, str(backend_dir))

    # 1. Export FastAPI OpenAPI schema
    try:
        from main import app
    except ImportError as e:
        print(f"Failed to import app from main.py: {e}", file=sys.stderr)
        sys.exit(1)

    openapi_schema = app.openapi()
    openapi_path = backend_dir / "openapi.json"
    with open(openapi_path, "w", encoding="utf-8") as f:
        json.dump(openapi_schema, f, indent=2)
    print(f"Exported OpenAPI JSON to {openapi_path}")

    # 2. Run openapi-typescript
    api_ts_path = generated_dir / "api.ts"
    npx_cmd = "npx.cmd" if os.name == "nt" else "npx"
    print("Running openapi-typescript...")
    try:
        subprocess.run(
            [npx_cmd, "--yes", "openapi-typescript", str(openapi_path), "-o", str(api_ts_path)],
            check=True,
        )
        print(f"Successfully generated {api_ts_path}")
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"Failed to run openapi-typescript: {e}", file=sys.stderr)
        sys.exit(1)

    # 3. Export Pydantic WebSocket schema -> json-schema-to-typescript
    print("Generating WebSocket message types...")
    try:
        from pydantic import TypeAdapter
        from snapland.core.domain.ws_messages import ClientMessage, ServerMessage

        ta = TypeAdapter(ClientMessage | ServerMessage)
        ws_schema = ta.json_schema()
        ws_schema["title"] = "WebSocketMessage"

        # Ensure discriminator field 'type' is required in all message schemas
        defs_key = next((k for k in ws_schema if "defs" in k), "$defs")
        for def_val in ws_schema.get(defs_key, {}).values():
            if isinstance(def_val, dict) and "properties" in def_val:
                if "type" in def_val["properties"]:
                    required = def_val.setdefault("required", [])
                    if "type" not in required:
                        required.append("type")

        ws_schema_path = backend_dir / "ws_schema.json"
        with open(ws_schema_path, "w", encoding="utf-8") as f:
            json.dump(ws_schema, f, indent=2)

        ws_ts_path = generated_dir / "ws.ts"
        subprocess.run(
            [npx_cmd, "--yes", "json-schema-to-typescript", str(ws_schema_path), "-o", str(ws_ts_path)],
            check=True,
        )
        if ws_schema_path.exists():
            ws_schema_path.unlink()
        print(f"Successfully generated {ws_ts_path}")
    except (subprocess.CalledProcessError, FileNotFoundError, ImportError) as e:
        print(f"Failed to generate WebSocket types: {e}", file=sys.stderr)
        sys.exit(1)

    print("Type generation complete.")


if __name__ == "__main__":
    main()
