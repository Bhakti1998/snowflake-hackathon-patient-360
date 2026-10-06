# Cortex Code CLI and Desktop reuse

Checked against official Snowflake documentation on 2026-10-05. Product versions
may differ; verify discovery in the installed applications before implementation.

## Open the right workspace

Use `CareLens360-Hackathon-Design` as the project root. Its root
[AGENTS.md](../AGENTS.md) is the persistent instruction entry point.
The parent workspace has only a small routing instruction file.

No global user files, `~/.snowflake/cortex/skills.json`, profiles, hooks,
credentials, or installed skills are changed by this project kit.

## One source of truth, two project paths

| Consumer | Project path in this kit | How used |
|---|---|---|
| CLI | `.cortex/skills/<name>/SKILL.md` | Documented project skill location |
| Desktop | `.snowflake/cortex/skills` | Relative directory link to the same canonical skills |
| Both | Root `AGENTS.md` | Project instructions |
| Both | `.cortex/memory/*.md` | Explicitly read through AGENTS and the memory skill |

The compatibility link is:

```text
.snowflake/cortex/skills -> ../../.cortex/skills
```

It stays inside the repository and contains no absolute machine path. Skills
are not duplicated. Resolve skill references relative to the canonical location
after following the link; do not reinterpret `../../../docs` from the alias.

## CLI

From a terminal in this repository, start the installed `cortex` CLI. Use
`/skill list` to verify the twelve project skills. Invoke by mentioning a skill
explicitly, for example:

```text
Use carelens-project-memory to load context and identify the next unblocked task.
Use document-evidence-extractor to plan the page-aware full-MVP pipeline.
Use clinical-question-evaluator to run the frozen golden question set.
```

Use the CLI's supported invocation syntax shown by your version if it differs.
Existing account connections are selected through normal Cortex configuration;
never place credentials in the skill files.

## Desktop

1. Open this repository as the workspace.
2. In **Agent Settings -> Rules -> Instruction Files**, confirm root AGENTS is
   listed with Workspace scope.
3. In **Agent Settings -> Skills**, confirm the project skills appear under
   Local Skills. Ask for a named skill and confirm a "Using skill" indication.
4. Confirm memory is loaded by asking for current blockers and source precedence.
   Memory Markdown is not itself automatically discovered as instruction files.
5. If your Desktop build does not follow the compatibility link, use **Local
   Skills -> + -> Add Local Skill** and select the canonical `.cortex/skills`
   directory itself. Do not select the repository root and expect recursive
   scanning through hidden directories.

Manual Local Skill registration is an opt-in user action and may write
`~/.snowflake/cortex/skills.json`; these documents do not perform it. Avoid
registering the same skills through multiple paths if duplicates appear.

## Parent workspace and other platforms

If keeping the outer `CoCo CLI Hackathon` folder open, follow the parent AGENTS
and register/select the nested repository's canonical skill directory explicitly,
or open the nested repository in a new workspace. Do not assume child project
skills are auto-discovered from an arbitrary parent workspace.

On Windows, a clone may materialize a symlink as a text file if symlink support
is unavailable. Register the canonical skill directory in Desktop instead.
CLI still uses the ordinary `.cortex/skills` files. Do not maintain a separate
edited skill copy to work around link support.

## Portable skill format

Each skill uses standard YAML `name` and `description` frontmatter, followed by
task instructions and links to shared project contracts. No surface-specific
`tools:` restriction is included: CLI calls SQL execution `sql_execute` while
Desktop may expose `snowflake_sql_execute`. Use the available authenticated
Snowflake tool instead of binding these Markdown skills to one runtime ID.

These are **developer-assistant skills**, not runtime clinical-agent tools.
Application guardrails must still be wired into `CARE_LENS_AGENT`.

## Verification and limits

- Confirm twelve skill names in CLI and Desktop, then invoke the memory skill.
- Confirm resolved documents are found from both discovery paths.
- Do not use `/skill sync` just to fix discovery: it can synchronize project
  content to global scope, which is not required here.
- Documentation and link validation do not prove app discovery, authentication,
  Snowflake feature availability, or successful deployment.
- Private distribution to a team Git repository or approved Snowflake stage
  is optional and requires approval. Local file skills are not automatically
  installed into Cortex Code in Snowsight.

## Official references

- [CLI extensibility and project skill locations](https://docs.snowflake.com/en/user-guide/cortex-code/extensibility)
- [Desktop skills and project/local registration](https://docs.snowflake.com/en/user-guide/cortex-code/cortex-code-desktop/skills)
- [Desktop instruction files](https://docs.snowflake.com/en/user-guide/cortex-code/cortex-code-desktop/instruction-files)
