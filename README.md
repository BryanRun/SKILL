# SKILL

A collection of Claude Code-first, agent-compatible skills for automotive middleware development workflows — covering code review, Gerrit integration, and Feishu document automation.

## Overview

| Skill | Description | Version |
|-------|-------------|---------|
| [enhanced_code_review](./enhanced_code_review/) | 6-dimension code review with Gerrit and local module support | 2.0.0 |
| [gerrit-pipeline](./gerrit-pipeline/) | One-click pipeline: submit → review → checklist → Feishu notification | 1.9.7 |
| [gerrit-submit](./gerrit-submit/) | Gerrit commit message generation, push, amend, and cherry-pick | - |
| [feishu-docs](./feishu-docs/) | Read, create, edit, and export Feishu (Lark) documents and whiteboards | - |

## Skills

### Enhanced Code Review

Full-featured code review engine with 6 mandatory dimensions:

1. **SOLID Principles** — Bob Martin APPP + Effective Java
2. **Security** — OWASP Top 10, CWE/SANS Top 25, ISO 21434
3. **Performance** — Effective Java Item 67, Android Performance Patterns
4. **Error Handling & Boundaries** — Effective Java Items 70-77, Clean Code Ch.7
5. **Code Quality & Style** — Google Java/C++ Style Guide
6. **Automotive Middleware** — Android Automotive, QNX, AUTOSAR, ISO 26262

Supports both Gerrit CR review (`review CR <number>`) and local module review (`review <module_path>`) without a CR number.

### Gerrit Pipeline

End-to-end pipeline that chains four steps in strict order:

```
Step 1: Code Submit    → Generate commit message + git push → CR number
Step 2: Code Review    → 6-dimension review + post to Gerrit
Step 3: Confirm        → Checklist + Feishu notification confirmation
Step 4: Feishu Notify  → Send result card to Feishu group chat after checklist succeeds
```

Each step can also be triggered independently.

### Gerrit Submit

Assists with Gerrit code submission workflows:

- Generate commit messages following company conventions (`【bug/change/feature】JIRA-ID: summary`)
- Push new Changes to Gerrit with configured reviewers
- Amend existing Changes (append patchset)
- Cherry-pick commits to other branches

### Feishu Docs

Interact with Feishu (Lark) cloud documents via Open Platform API:

- Create, read, edit, and export documents
- Import Markdown with auto-beautification (PlantUML/Mermaid to whiteboard, table formatting)
- Whiteboard operations (create nodes, import diagrams)
- Document permission management and Wiki integration

## Prerequisites

- Claude Code CLI/IDE extension for the best native skill experience, or another compatible agent that can read skill docs, run shell/Python scripts, and ask the user for confirmations
- Python 3.10+ (for automation scripts)
- Git with SSH access to Gerrit (for Gerrit-related skills)

### Environment Variables

| Variable | Required By | Description |
|----------|-------------|-------------|
| `GERRIT_BASE` | enhanced_code_review | Gerrit server base URL |
| `GERRIT_USER` | enhanced_code_review | Gerrit username |
| `GERRIT_HTTP_PASSWORD` | enhanced_code_review | Gerrit HTTP password |
| `FEISHU_APP_ID` | feishu-docs, gerrit-pipeline | Feishu app ID |
| `FEISHU_APP_SECRET` | feishu-docs, gerrit-pipeline | Feishu app secret |

## Installation

For Claude Code, copy or symlink the desired skill directories into your Claude Code skills directory:

```bash
# Example: install all skills
cp -r enhanced_code_review feishu-docs gerrit-pipeline gerrit-submit ~/.claude/skills/
```

For other agents, install the same directories into that agent's skill/plugin location and keep script paths resolvable from the skill directory.

## Usage

Skills are invoked through Claude Code via natural language or slash commands. Other compatible agents can use the same explicit natural-language commands; slash commands are a Claude Code optimization when supported.

```
# Code review via Gerrit CR number
review CR 993636

# Local module review (no CR needed)
review frameworks/cm/videoplayer

# Full pipeline: submit + review + checklist + notify
gerrit pipeline

# Submit code to Gerrit
gerrit submit

# Import Markdown to Feishu document
导入 Markdown 到飞书
```

## Project Structure

```
.
├── enhanced_code_review/
│   ├── SKILL.md              # Skill definition and instructions
│   ├── references/           # Review dimension reference docs (01-09)
│   └── scripts/              # Python automation scripts
├── feishu-docs/
│   ├── SKILL.md              # Skill definition
│   ├── api-reference.md      # Feishu API reference
│   └── scripts/              # feishu_client.py
├── gerrit-pipeline/
│   ├── SKILL.md              # Skill definition
│   └── scripts/              # Pipeline step scripts
└── gerrit-submit/
    └── SKILL.md              # Skill definition
```

## License

This project is proprietary. All rights reserved.
