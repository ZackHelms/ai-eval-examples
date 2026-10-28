---
name: <kebab-case-agent-name>
description: <One or two sentences: what this agent owns and WHEN to use it —
  the "use when" clause is what routing decisions read. Include "use
  proactively when …" if sessions should reach for it unprompted.>
model: <haiku | sonnet | opus — cheapest tier that produces correct output;
  see .claude/skills/task-scoping.md's rubric and the agent-tiering note in
  agents/README.md>
tools: <minimal toolset, e.g. Read, Grep, Glob for reviewers; add Bash/Edit
  only when the role genuinely writes>
---

# <Agent name> — <one-line role>

## Purpose

What this agent owns (its domain, its eval/standards surfaces) and the
boundary of that ownership — what it must NOT touch.

## Procedure

The steps the agent follows, numbered, deterministic where possible. Name
the exact files/skills it must read before acting.

## Output contract

What the agent returns to its caller: shape, required sections, and the
machine-readable lines (key=value) if any. An agent whose output can't be
consumed mechanically is a chat, not a tool.

## Escalation

What it does when blocked or when the task exceeds its tier: what it
reports, and to whom (usually: return findings + a recommendation, never
silently exceed scope).
