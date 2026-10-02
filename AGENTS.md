# Agent Guidelines & Repository Conventions

## Git Commit Conventions (Google Style)
* **Imperative Subject Line**: Write the first line as a standalone command/order (e.g. `Route incoming senders...`, not `Routed` or `Routing`), under 50 characters when possible (hard limit 72 characters). Do not use conventional commit tags like `feat:`, `fix:`, etc., and do not end the subject with a period.
* **Line Wrapping (72 Columns)**: Hard wrap all body lines at 72 characters (never exceed 80 characters). When passing commit messages via shell commands, include explicit newline breaks (`\n`) so lines are never stored as single continuous unwrapped paragraphs.
* **Explain the "Why"**: Use the body (separated from the subject by a blank line) to explain the motivation, context, and problem solved rather than repeating what is obvious from the code diff.
* **Brevity & Proportionality**: Keep descriptions concise and proportionate to the change—typically 1 to 2 focused sentences in the body. Avoid laundry lists or novels.
* **No Task Numbers**: Do not reference roadmap task numbers (e.g. `Task 27`) in commit messages; focus on architectural and functional descriptions.

## Todoist API Reference & Versioning
* **Primary API Documentation**: Always reference the official **Todoist REST API v1** documentation at `https://developer.todoist.com/api/v1/`.
* **Legacy Sync v9 Deprecation**: Do not use legacy `sync/v9` endpoints (`https://api.todoist.net` or `https://api.todoist.com/sync/v9/`). They return `HTTP 410 Gone / Deprecated`.
* **Core Endpoints**:
  - Projects: `GET https://api.todoist.com/api/v1/projects` & `GET https://api.todoist.com/api/v1/projects/archived` (cursor-paginated via `next_cursor`).
  - Activities: `GET https://api.todoist.com/api/v1/activities` (supports `object_type=item`, `event_type=completed`, `date_from`, `date_to`, `cursor`).
  - Task Lookup: `GET https://api.todoist.com/api/v1/tasks/{task_id}` (resolves task content and `parent_id` for both active and completed tasks).

## Strict Read-Only & Non-Destructive Policy
* **Read-Only Operations Only**: `todoist-trace` is strictly an export, inspection, and trace tool. It must **never** mutate, create, update, close, reopen, or delete any user data.
* **HTTP Method Enforcement**: Use HTTP `GET` exclusively (`requests.get`). Never issue `POST`, `PUT`, `PATCH`, or `DELETE` requests against the Todoist API.
* **Zero Modification**: No tasks, projects, sections, comments, or labels may ever be modified, archived, unarchived, or deleted.


