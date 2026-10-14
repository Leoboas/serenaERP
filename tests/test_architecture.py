import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[1]
APP_ROOT = PROJECT_ROOT / "app"
CORE_LAYERS = ("domain", "application")

# Keep framework and infrastructure adapters at the system boundary. The core may
# depend on the standard library and other core modules only.
FORBIDDEN_EXTERNAL_ROOTS = {
    "aioboto3",
    "aws_lambda_powertools",
    "awswrangler",
    "boto3",
    "botocore",
    "celery",
    "fastapi",
    "kombu",
    "pydantic",
    "pydantic_settings",
    "redis",
    "sagemaker",
    "sqlalchemy",
    "starlette",
}
FORBIDDEN_APP_PREFIXES = ("app.api", "app.infrastructure", "app.workers")


def _relative_import_base(source_path: Path, level: int) -> str:
    """Resolve an ``ImportFrom`` package relative to an app source file."""
    package_parts = source_path.parent.relative_to(PROJECT_ROOT).parts
    return ".".join(package_parts[: len(package_parts) - level + 1])


def _imported_modules(source_path: Path, node: ast.Import | ast.ImportFrom) -> set[str]:
    if isinstance(node, ast.Import):
        return {alias.name for alias in node.names}

    if node.level:
        base = _relative_import_base(source_path, node.level)
        if node.module:
            return {f"{base}.{node.module}" if base else node.module}
        return {f"{base}.{alias.name}" if base else alias.name for alias in node.names}

    return {node.module} if node.module else set()


def _is_forbidden(module_name: str) -> bool:
    root = module_name.split(".", maxsplit=1)[0]
    imports_outer_layer = any(
        module_name == prefix or module_name.startswith(f"{prefix}.") for prefix in FORBIDDEN_APP_PREFIXES
    )
    return root in FORBIDDEN_EXTERNAL_ROOTS or imports_outer_layer


def test_core_layers_have_no_framework_or_outer_layer_dependencies() -> None:
    violations: list[str] = []

    for layer in CORE_LAYERS:
        source_paths = sorted((APP_ROOT / layer).rglob("*.py"))
        assert source_paths, f"Camada app/{layer} sem arquivos Python para auditar"

        for source_path in source_paths:
            tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
            for node in ast.walk(tree):
                if not isinstance(node, (ast.Import, ast.ImportFrom)):
                    continue
                for module_name in _imported_modules(source_path, node):
                    if _is_forbidden(module_name):
                        relative_path = source_path.relative_to(PROJECT_ROOT)
                        violations.append(f"{relative_path}:{node.lineno} imports {module_name}")

    assert not violations, "Architecture boundary violations:\n" + "\n".join(violations)
