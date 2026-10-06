"""Command-line entry point; account mutations always require explicit flags."""

import argparse
import json
from pathlib import Path

from .dataset import generate
from .deploy import Deployment, connect
from .sql import ENTITIES, curated, foundation, governed, load_sql, semantics
from .verify import verify


def main():
    parser = argparse.ArgumentParser(description="CareLens360 synthetic MVP workflow")
    parser.add_argument("--config", type=Path, default=Path("config/workflow.json"))
    commands = parser.add_subparsers(dest="command", required=True)
    gen = commands.add_parser("generate")
    gen.add_argument("--seed-folder", type=Path, required=True)
    gen.add_argument("--output", type=Path, default=Path("data/generated/v5"))
    render = commands.add_parser("render-sql")
    render.add_argument("--output", type=Path, default=Path("build/workflow.sql"))
    check = commands.add_parser("check-access")
    check.add_argument("--authenticator")
    deploy = commands.add_parser("deploy")
    deploy.add_argument("--warehouse", required=True)
    deploy.add_argument("--data", type=Path, default=Path("data/generated/v5"))
    deploy.add_argument("--phase", choices=["base", "procedure", "parse", "services", "roles", "app", "verify", "all"], required=True)
    deploy.add_argument("--parse-limit", type=int, default=10)
    deploy.add_argument("--authenticator")
    deploy.add_argument("--apply", action="store_true")
    deploy.add_argument("--confirm-database", required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    repository = Path(__file__).resolve().parents[2]
    if args.command == "generate":
        result = generate(args.seed_folder, args.output, config)
        print(json.dumps({"counts": result["counts"], "documents": result["document_count"]}, indent=2))
        return
    if args.command == "render-sql":
        statements = foundation(config["database"])
        statements += [s for e in ENTITIES for s in load_sql(config["database"], e)]
        statements += curated(config["database"], config) + governed(config["database"])
        statements += [semantics(config["database"])]
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(";\n\n".join(statements) + ";\n")
        print("Rendered SQL; no account execution performed:", args.output)
        return
    if args.command == "check-access":
        with connect(config["connection_name"], args.authenticator) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT CURRENT_ROLE(), CURRENT_WAREHOUSE(), CURRENT_REGION()")
                print("Role, warehouse, region:", cursor.fetchone())
        return
    if not args.apply or args.confirm_database != config["database"]:
        parser.error("Deployment requires --apply and exact --confirm-database")
    if args.phase in ("base", "all"):
        metadata = json.loads((args.data / "manifest.json").read_text())
        if metadata["config"] != config:
            raise ValueError("Dataset config differs from deployment config; regenerate or select matching version")
    with connect(config["connection_name"], args.authenticator) as connection:
        workflow = Deployment(connection, config, args.warehouse, repository / "evidence/execution")
        phases = ["base", "procedure", "parse", "services", "roles", "app"] if args.phase == "all" else [args.phase]
        for phase in phases:
            if phase != "base":
                workflow.require_managed()
            if phase == "base":
                workflow.base(args.data)
            elif phase == "procedure":
                workflow.procedure(repository)
            elif phase == "parse":
                print(workflow.parse(args.parse_limit))
            elif phase == "services":
                remaining = workflow.execute(f"""SELECT COUNT(*) FROM {workflow.db}.RAW.DOCUMENT_MANIFEST m
                  WHERE NOT EXISTS(SELECT 1 FROM {workflow.db}.CURATED.DOCUMENT_CHUNKS c
                    WHERE c.DOCUMENT_ID=m.ID AND c.SHA256=m.DATA:sha256::STRING)""")[0][0]
                if remaining:
                    raise RuntimeError(f"{remaining} documents unparsed; finish parsing before services")
                workflow.search_and_agents()
            elif phase == "roles":
                workflow.roles()
            elif phase == "app":
                workflow.app(repository)
            elif phase == "verify":
                print("Account verification:", verify(workflow, args.data))
        print("Executed phases:", phases, "Evidence:", workflow.log)


if __name__ == "__main__":
    main()
