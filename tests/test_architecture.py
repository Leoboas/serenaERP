import ast
from pathlib import Path

FORBIDDEN_DOMAIN_IMPORTS = {"fastapi", "sqlalchemy", "pydantic"}


def test_domain_has_no_framework_dependencies() -> None:
    domain_path = Path(__file__).parents[1] / "app" / "domain"
    for source_path in domain_path.glob("*.py"):
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported = {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported = {node.module.split(".")[0]}
            else:
                continue
            assert imported.isdisjoint(FORBIDDEN_DOMAIN_IMPORTS), source_path
