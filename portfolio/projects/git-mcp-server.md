---
id: git-mcp-server
type: project
title:
  en: "grounded-git-mcp: a local Git MCP server with human approval for writes"
  he: "grounded-git-mcp: שרת MCP מקומי ל-Git, עם אישור אנושי לכל כתיבה"
aliases: ["MCP", "MCP server", "Model Context Protocol", "Git", "SafeGitRunner", "AI agents", "human in the loop", "approval flow", "confirmation token", "safe automation", "שרת MCP", "סוכני AI", "אדם בלולאה", "אישור אנושי", "אוטומציה בטוחה"]
period: "2025"
role: "Sole developer, personal project"
tech: [Python, MCP, FastMCP, Git, pytest, GitHub Actions, uv]
tags: [ai-agents, mcp, security, developer-tools]
metrics: []
architecture:
  components:
    - { id: agent, label: "AI agent (e.g. Claude Desktop)" }
    - { id: server, label: "MCP server: 10 tools, 3 read-only resources" }
    - { id: classify, label: "Risk classification (low / medium / high / critical)" }
    - { id: store, label: "Confirmation store + audit log (.grounded_git_mcp/)" }
    - { id: runner, label: "SafeGitRunner (no shell, allowlist, timeout, output ceiling)" }
    - { id: repo, label: "Local Git repository" }
    - { id: user, label: "User" }
  edges:
    - { from: agent, to: server, label: "MCP tool calls" }
    - { from: server, to: runner, label: "read-only commands" }
    - { from: server, to: classify, label: "proposed write" }
    - { from: classify, to: store, label: "one-time token" }
    - { from: user, to: server, label: "I CONFIRM <id>" }
    - { from: store, to: runner, label: "preconditions hold" }
    - { from: runner, to: repo, label: "git, cwd = root" }
code_allowed: false                        # described only, no code snippets
depth: full                                # chapter 3 planned overview before the code was available
related: [human-gated-translation]
answers:
  - "Has she built an MCP server?"
  - "How does she let an AI agent touch a repository without risk?"
  - "איך היא מונעת מסוכן AI להריץ פקודות מסוכנות?"
  - "מה זה SafeGitRunner?"
review:
  approved: true
  approved_on: 2026-11-04
  publication_check: own-project
---

## Problem

AI agents that debug or explore code need the real, current state of a repository: the working tree, uncommitted changes and the full Git history, not a stale snapshot or a remote API. But an agent that can run Git commands can also change or destroy a repository. grounded-git-mcp is a local MCP server that gives agents that access, while it never runs a write operation on its own.

## Why it was hard

Agents need real access to the repository to be useful, yet nothing they do may change it without a person's explicit approval, on the exact state that person reviewed. A command that looks like a read can still mutate state, and a Git process can hang on a prompt or run forever.

## My role

Sarah built the whole server on her own, as a personal project.

## Architecture

The server is built on FastMCP. It exposes 10 tools (repository info, status, diff summary, log, show commit, grep, blame, conflict detection, propose a command, execute a confirmed command) and 3 read-only resources: the tree at a reference, a file at a reference, and the diff between two references. Tool and resource descriptions are written for the model, as part of the contract that guides it to the right tool.

**SafeGitRunner** is the single point through which every Git command runs. It never uses a shell, always runs in the repository root, and sets a non-interactive environment (no credential prompts, no pager, a fixed locale) so the agent never hangs. Each command has a hard timeout; a stuck process is killed with its whole process tree (on Windows) or process group (on POSIX). Output has a ceiling, truncated deterministically. In read-only mode, only an allowlist of subcommands runs, and flags that can mutate state are blocked, such as `--global`, `--force`, branch or tag deletion, remote changes and config writes.

**Risk classification:** read commands are low risk and run immediately. Write commands are medium or high risk and only go through approval. Network commands are high risk. Destructive commands such as `reset`, `clean`, `rebase` and `push` are critical: the server rejects them, and the agent can only explain what the user should run.

**Approval flow:** proposing a write returns a one-time confirmation token, valid for 30 minutes. The token is bound to the exact command through a SHA-256 hash of its arguments, and to the repository state the user reviewed: HEAD, optionally the branch and a clean working tree, and no conflicts. Execution requires the exact phrase `I CONFIRM <id>`, and fails if the token expired, was used, the hash does not match, or the repository changed since approval. Proposals and executions are written to an append-only audit log, and the confirmations file is written atomically.

**Tests:** unit, integration (against a dummy repository) and schema snapshot tests, run in GitHub Actions on every push and pull request. The server was also validated end to end with the MCP Inspector.

## Decisions and alternatives

**Arguments as a list, never a shell string.** Rejected: joining the command into a shell string. Why: a joined string is ambiguous when arguments contain spaces or quotes, and opens the door to injection.

**Bind the approval to the repository state.** The token is checked against the HEAD, branch and cleanliness the user saw, so a command approved on one state cannot run on another.

**One-time tokens.** Each approval can be used once, so the same approval cannot be replayed.

## Results

The server works end to end with Claude Desktop and the MCP Inspector, and an agent can find a regression through history, diff and blame, then propose a minimal fix without executing anything.
