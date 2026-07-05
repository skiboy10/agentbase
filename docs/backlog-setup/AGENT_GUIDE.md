# Agent Interaction Guide — GitHub Issues Backlog

This guide tells Claude agents (and humans) how to interact with the Agentbase backlog on GitHub Issues.

## Prerequisites

The `gh` CLI must be installed and authenticated. Verify with: `gh auth status`

## Repository

```
REPO="skiboy10/agentbase"
```

## Reading the Backlog

### List open issues (default: most recent)
```bash
gh issue list --repo $REPO --limit 30
```

### Filter by label
```bash
# All critical bugs
gh issue list --repo $REPO --label "priority: critical" --label "type: bug"

# All Security Hardening work
gh issue list --repo $REPO --milestone "Security Hardening"

# Everything in the RAG area
gh issue list --repo $REPO --label "area: rag"

# Blocked items
gh issue list --repo $REPO --label "status: blocked"
```

### Read a specific issue (with comments)
```bash
gh issue view 42 --repo $REPO --comments
```

### Search issues
```bash
gh issue list --repo $REPO --search "knowledge freshness"
```

## Creating Issues

Always include: type label, area label, priority label, and a clear description.
**Always add the new issue to the project board** after creating it.

```bash
# NOTE: Use two-step variable pattern — macOS bash 3.2 has a known bug
# with heredocs inside $(command substitution). Do NOT use --body "$(cat <<'EOF'...)".
body=$(cat <<'EOF'
## Problem
What's wrong or missing, and why it matters.

## Acceptance Criteria
- [ ] Criterion 1
- [ ] Criterion 2

## Context
Links to relevant docs, other issues, or code.
EOF
)
gh issue create --repo $REPO \
  --title "Short, imperative title describing the change" \
  --label "type: feature,area: backend,priority: high,size: M" \
  --milestone "Active Sprint" \
  --body "$body"

# Add to project board (IMPORTANT — issues don't auto-appear on the board)
gh project item-add 2 --owner skiboy10 --url https://github.com/$REPO/issues/ISSUE_NUMBER
```

> **Tip:** The `gh issue create` command prints the issue URL. Use that URL directly in the `gh project item-add` command.

### Issue Title Conventions
- Use imperative mood: "Add X", "Fix Y", "Refactor Z"
- Prefix bugs with `[Bug]`
- Keep under 80 characters

### Required Labels (pick one from each)

**Type** (what kind of work):
`type: feature` | `type: enhancement` | `type: bug` | `type: tech-debt` | `type: docs` | `type: infra`

**Area** (which part of the system):
`area: backend` | `area: frontend` | `area: rag` | `area: knowledge` | `area: agents` | `area: mcp` | `area: providers` | `area: infra` | `area: api`

**Priority**:
`priority: critical` | `priority: high` | `priority: medium` | `priority: low`

### Optional Labels

**Size** (estimation):
`size: S` (< 1 day) | `size: M` (1-3 days) | `size: L` (3-5 days) | `size: XL` (> 1 sprint)

**Status** (supplemental state):
`status: blocked` | `status: needs-design` | `status: needs-review`

### Milestones (roadmap phases)
- `Security Hardening`
- `Code Health`
- `RAG Pipeline`
- `Knowledge Lifecycle`
- `Platform Features`
- `Distribution & Scale`
- `Active Sprint`

## Updating Issues

### Add a comment
```bash
gh issue comment 42 --repo $REPO --body "Status update: completed the refactor. Tests passing."
```

### Add or change labels
```bash
gh issue edit 42 --repo $REPO --add-label "status: blocked"
gh issue edit 42 --repo $REPO --remove-label "status: blocked"
```

### Close an issue
```bash
gh issue close 42 --repo $REPO --comment "Resolved in commit abc1234."
```

### Reassign
```bash
gh issue edit 42 --repo $REPO --add-assignee username
```

## Agent Behavior Guidelines

When a Claude agent works on a task from this backlog:

1. **Before starting:** Comment on the issue that work is beginning. Add the assignee.
2. **During work:** If scope changes or blockers arise, comment with details.
3. **On completion:** Comment with a summary of what was done and reference the commit(s). Close the issue.
4. **If blocked:** Add the `status: blocked` label and comment explaining what's needed.
5. **If new work is discovered:** Create a new issue (don't silently expand scope). Reference the parent issue.

### Referencing Issues in Commits
Include `Fixes #42` or `Relates to #42` in commit messages to auto-link.

## Common Agent Workflows

### "What should I work on next?"
```bash
# Highest priority open items not blocked
gh issue list --repo $REPO --label "priority: critical" --state open | grep -v "status: blocked"
gh issue list --repo $REPO --label "priority: high" --state open | grep -v "status: blocked"
```

### "What's the status of Security Hardening?"
```bash
gh issue list --repo $REPO --milestone "Security Hardening" --state all
```

### "Are there any bugs?"
```bash
gh issue list --repo $REPO --label "type: bug" --state open
```

### "What's blocked?"
```bash
gh issue list --repo $REPO --label "status: blocked" --state open
```
