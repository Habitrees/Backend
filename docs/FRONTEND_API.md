# Habitree backend API

## Conventions

- Paths have trailing slashes. JSON bodies use `Content-Type: application/json`. Dates use `YYYY-MM-DD` and timestamps include an offset.
- **Bearer** means `Authorization: Bearer <access-token>`. **Cookie + CSRF** means send credentials and `X-CSRFToken` on POST. **Workflow** means a service credential in `X-Workflow-Token`.
- Bearer endpoints can return **401** for absent or invalid access tokens. API requests can return **400** for malformed input, **429** for throttling, and **500** for server errors. The tables list additional endpoint-specific outcomes. Validation errors use field names or `non_field_errors` as keys. Other errors generally return `{"detail":"..."}`. A **204** response has an empty body.
- **Page** means `page` (one-based) and `page_size` (default 25, max 100). The envelope has `count`, `next`, `previous`, and `results`. **Optional page** preserves the array response unless either paging parameter is supplied. An unavailable page returns **404**.
- A dash in the query or body columns means the operation has no documented parameters of that type.

## Authentication and profile

All paths below start with `/api/auth/`.

| Method and path | Access | Query | JSON body | Success and function | Additional errors |
| --- | --- | --- | --- | --- | --- |
| GET `csrf/` | Public | — | — | 200 `{csrfToken}` and CSRF cookie | — |
| POST `register/send-otp/` | Public | — | `phone` | 200 `{detail, expires_in, resend_after}` after sending the code | 409 registered, 502 provider failure |
| POST `register/verify-otp/` | Public | — | `phone, code` | 200 `{detail, registration_token, expires_in}` | 409 account conflict |
| POST `register/complete/` | Cookie + CSRF, signed registration token | — | `registration_token, username, full_name, password, confirm_password, timezone, locale, terms_accepted` | 201 `{detail, user, access}`, with refresh cookie | 403 CSRF, 409 account conflict |
| POST `login/` | Cookie + CSRF | — | `phone, password`, optional `remember_me` | 200 `{detail, user, access}`, with refresh cookie | 400 invalid credentials, 403 CSRF |
| POST `token/refresh/` | Cookie + CSRF | — | — | 200 `{access, detail}` | 401 missing, invalid or blacklisted refresh token, 403 CSRF |
| POST `token/blacklist/` | Cookie + CSRF | — | — | 200 `{detail}`, clears refresh cookie | 403 CSRF |
| POST `password-reset/send-otp/` | Public | — | `phone` | 200 `{detail, expires_in, resend_after}`, generic request acknowledgement | — |
| POST `password-reset/verify-otp/` | Public | — | `phone, code` | 200 `{detail, reset_token, expires_in}` | — |
| POST `password-reset/confirm/` | Public, signed reset token | — | `reset_token, new_password, confirm_password` | 200 `{detail}`, resets credentials | — |
| GET `profile/` | Bearer, self | — | — | 200 Profile | — |
| PATCH `profile/` | Bearer, self | — | Any of `username, full_name, timezone, locale, ai_coach_enabled` | 200 Profile | — |

Profile returns `id, phone, username, full_name, timezone, locale, phone_verified_at, created_at, ai_coach_enabled`. The auth response's `user` has `id, phone, username, full_name`.

## Personal and public challenges

| Method and path | Access | Query | JSON body | Success and function | Additional errors |
| --- | --- | --- | --- | --- | --- |
| GET `/api/challenges/` | Bearer, owner | Optional page | — | 200 Challenge list, excludes archived | 404 invalid page |
| POST `/api/challenges/` | Bearer | — | Challenge input | 201 Challenge | — |
| GET `/api/challenges/{id}/` | Bearer, owner | — | — | 200 Challenge | 404 unavailable |
| PATCH `/api/challenges/{id}/` | Bearer, owner | — | Challenge input subset | 200 Challenge | 404 unavailable |
| DELETE `/api/challenges/{id}/` | Bearer, owner | — | — | 204 archives the challenge | 404 unavailable |
| GET `/api/challenges/{id}/schedule/` | Bearer, owner | — | — | 200 schedule with frequency, local today, challenge dates, and current period bounds | 404 unavailable |
| GET `/api/challenges/{id}/logs/` | Bearer, owner | — | — | 200 HabitLog array | 404 unavailable |
| PUT `/api/challenges/{id}/logs/{log_date}/` | Bearer, owner | — | Habit input | 200 updates or 201 creates HabitLog | 404 unavailable |
| GET `/api/challenges/{id}/streak/` | Bearer, owner | — | — | 200 Streak | 404 unavailable |
| POST `/api/challenges/{id}/recover/{log_date}/` | Bearer, owner | — | Habit input | 200 recovered HabitLog | 404 unavailable |
| GET `/api/challenges/{id}/plant/` | Bearer, owner | — | — | 200 Plant | 404 unavailable |
| GET `/api/garden/` | Bearer, self | — | — | 200 `{total_growing,total_completed,growing,completed}` with Plant arrays | — |
| GET `/api/dashboard/` | Bearer, self | — | — | 200 Dashboard | — |
| GET `/api/public-challenges/` | Bearer | Page, `category, difficulty, duration_days, min_duration_days, max_duration_days, ordering` | — | 200 published PublicChallenge page | 404 invalid page |
| GET `/api/public-challenges/{id}/` | Bearer | — | — | 200 published PublicChallenge | 404 missing or unpublished |
| POST `/api/public-challenges/{id}/join/` | Bearer | — | — | 201 creates a personal Challenge and increments popularity. 200 returns the existing unarchived Challenge | 404 missing or unpublished |

- **Challenge input** uses `title, description, polarity, kind, target_value, unit, start_date, duration_days, frequency, mode`. The response adds `id, end_date, timezone, status, archived, created_at, updated_at`. Kinds are `binary, count, time`. Frequencies are `daily, weekly, monthly`. Modes are `strict, flexible`.
- **Habit input** contains `performed` for binary habits or `value` for numeric habits. HabitLog returns `id, challenge, period_start, value, performed, success, recovered_at, created_at, updated_at`.
- **Streak** returns `current_streak, best_streak, consecutive_failures, current_period_success, recovery_pending, recoverable_date, can_recover`. **Plant** returns `challenge_id, challenge_title, stage, stage_key, status, total_periods, successful_periods, progress_percent, completed`.
- **Dashboard** returns `user, summary, active_challenges, weekly_summary, monthly_summary, active_groups, recommended_challenges, motivational_message`. Active challenges have today's period and status, streak, plant, and success rate. Summaries use the last 7 and 30 completed challenge-local days. Recommended challenges are up to five published templates ordered by popularity, excluding templates with an unarchived personal copy.
- **PublicChallenge** returns `id, title, description, category, difficulty, kind, polarity, target_value, unit, duration_days, frequency, mode, published, popularity, created_at, updated_at`. Ordering values are `popular` (default), `newest`, `duration_asc`, and `duration_desc`. Duration filters accept 1–366 days. An archived personal copy permits another join under the existing challenge lifecycle.

## Groups and chat

All routes require Bearer access unless specified. Group and nested-resource lookups require current membership where noted. Below, `G` is `/api/groups/{group_id}/` and `C` is `/api/groups/{group_id}/challenges/{id}/`.

| Method and path | Permission | Query | JSON body | Success and function | Additional errors |
| --- | --- | --- | --- | --- | --- |
| GET `/api/groups/` | Member of each returned group | Optional page | — | 200 Group list | 404 invalid page |
| POST `/api/groups/` | Authenticated | — | `name, description, visibility` | 201 Group with creator as owner | — |
| GET `/api/groups/discover/` | Authenticated | `public_id` UUID | — | 200 public group with `id,name,description,visibility,public_id` | 404 missing or private |
| POST `/api/groups/join/` | Authenticated | — | `public_id` UUID | 200 GroupMembership | 404 missing or private |
| GET `G` | Member | — | — | 200 Group detail | 404 unavailable |
| PATCH `G` | Owner | — | `name, description, visibility` subset | 200 Group | 403 role, 404 unavailable |
| POST `G/leave/` | Non-owner member | — | — | 204 leaves group and revokes chat access | 400 owner, 404 unavailable |
| GET `G/members/` | Member | — | — | 200 GroupMembership array | 404 unavailable |
| POST `G/members/` | Owner or admin with member-management permission | — | `username` | 201 GroupMembership | 403 role, 404 group or user |
| PATCH `G/members/{user_id}/` | Owner | — | `role, can_manage_members, can_manage_challenges, can_warn_members` subset | 200 GroupMembership | 403 role, 404 group or user |
| DELETE `G/members/{user_id}/` | Owner or authorized admin. Only owner can remove an admin | — | — | 204 removes member and revokes chat access | 403 role, 404 group or user |
| GET `G/messages/` | Member | `before_id, limit` (default 50, max 100) | — | 200 `{messages,has_more,next_before_id}`. Items in each page are oldest first | 404 unavailable |
| GET `G/challenges/` | Member | Optional page | — | 200 GroupChallenge list | 404 unavailable or invalid page |
| POST `G/challenges/` | Owner or admin with challenge-management permission | — | GroupChallenge input | 201 GroupChallenge | 403 role, 404 unavailable |
| GET `C` | Member | — | — | 200 GroupChallenge | 404 unavailable |
| PATCH `C` | Owner or admin with challenge-management permission | — | GroupChallenge input subset | 200 GroupChallenge | 403 role, 404 unavailable |
| GET `C/schedule/` | Member | — | — | 200 schedule with local period bounds | 404 unavailable |
| GET `C/logs/` | Member, own logs | — | — | 200 GroupHabitLog array | 404 unavailable |
| PUT `C/logs/{log_date}/` | Member, own logs | — | Habit input | 200 updates or 201 creates GroupHabitLog | 404 unavailable |
| GET `C/progress/` | Member | — | — | 200 member progress array with period totals, progress percent, streaks, failure count, and policy flag | 404 unavailable |
| POST `C/apply-policy/` | Owner or authorized admin for the configured policy | — | `user_id` | 200 `{action,user_id,warning_id}` | 403 role, 404 group, challenge or user |
| GET `C/warnings/` | Member, own warnings | — | — | 200 warnings with challenge, issuer, period, failure count, message and creation timestamp | 404 unavailable |

Append each suffix to the prefix using a single slash. Group responses carry `id, owner, name, description, visibility, public_id, created_at, updated_at`. Membership responses carry `id, group, user, username, full_name, role, can_manage_members, can_manage_challenges, can_warn_members, joined_at`. GroupChallenge input uses the Challenge input fields other than `mode`, plus `failure_policy, failure_limit` where the serializer allows changes. The response adds `group` and returns the server-controlled `mode` and `timezone`. GroupHabitLog includes `id, challenge, membership, period_start, value, performed, success, created_at, updated_at`.

**WebSocket** `/ws/groups/{group_id}/chat/` requires an allowed Origin. After `{"type":"auth_required"}`, send `{"type":"auth","access_token":"..."}`. After `auth_ok`, send `{"type":"message","text":"..."}` with 1–2000 characters. Persisted messages arrive as `{"type":"message","message":{...}}` with `id, group, sender, username, full_name, text, created_at`. Authentication failures close with 4401, access revocation with 4403, and invalid frame types or oversize frames with 4400. Structured `error` events include a machine-readable `code`.

## Reminders and notifications

| Method and path | Access | Query | JSON body | Success and function | Additional errors |
| --- | --- | --- | --- | --- | --- |
| GET `/api/reminders/` | Bearer, challenge owner | Optional page, `challenge` ID | — | 200 Reminder list | 404 invalid page |
| POST `/api/reminders/` | Bearer, challenge owner | — | `challenge, local_time`, optional `message, enabled` | 201 Reminder | 404 unavailable challenge |
| GET `/api/reminders/{id}/` | Bearer, owner | — | — | 200 Reminder | 404 unavailable |
| PATCH `/api/reminders/{id}/` | Bearer, owner | — | `local_time, message, enabled` subset | 200 Reminder | 404 unavailable |
| DELETE `/api/reminders/{id}/` | Bearer, owner | — | — | 204 removes reminder | 404 unavailable |
| GET `/api/notification-preferences/` | Bearer, self | — | — | 200 preferences | — |
| PATCH `/api/notification-preferences/` | Bearer, self | — | `in_app_enabled, push_enabled, email_reports_enabled, telegram_reports_enabled` subset | 200 preferences | — |
| GET `/api/notifications/` | Bearer, recipient | Page | — | 200 Notification page, newest first | 404 invalid page |
| POST `/api/notifications/{id}/read/` | Bearer, recipient | — | — | 200 Notification with `read_at` | 404 unavailable |
| POST `/api/notifications/read-all/` | Bearer, recipient | — | — | 200 `{updated}` | — |

Reminder returns `id, challenge, local_time, timezone, message, enabled, created_at, updated_at`. Notification returns `id, title, message, created_at, read_at`. Schedule `python manage.py deliver_reminders` periodically to deliver in-app reminders once per reminder and challenge-local date during its schedule. Database write failures record a delivery error and yield a nonzero command exit. The stored push preference is available for future PWA integration. Web Push delivery and subscriptions require confirmed PWA requirements and infrastructure.

## Reports and AI Coach

| Method and path | Access | Query | JSON body | Success and function | Additional errors |
| --- | --- | --- | --- | --- | --- |
| GET `/api/reports/{period}/` | Bearer, self | `date`, `export=csv\|pdf`, `language=en\|fa` | — | 200 Report JSON or attachment | 404 unknown period |
| GET `/api/coach/conversations/` | Bearer, AI-enabled owner | Page | — | 200 Conversation page | 403 opt-in required, 404 invalid page |
| POST `/api/coach/conversations/` | Bearer, AI-enabled | — | `title` | 201 Conversation | 403 opt-in required |
| GET `/api/coach/conversations/{id}/` | Bearer, AI-enabled owner | — | — | 200 Conversation | 403 opt-in required, 404 unavailable |
| GET `/api/coach/conversations/{id}/messages/` | Bearer, AI-enabled owner | Page | — | 200 Message page, newest first | 403 opt-in required, 404 unavailable or invalid page |
| POST `/api/coach/conversations/{id}/messages/` | Bearer, AI-enabled owner | — | `text` (max 4,000) | 201 stored Message, queued for n8n polling | 403 opt-in required, 404 unavailable |
| GET `/api/coach/proposals/{id}/` | Bearer, AI-enabled owner | — | — | 200 Proposal | 403 opt-in required, 404 unavailable |
| POST `/api/coach/proposals/{id}/accept/` | Bearer, AI-enabled owner | — | — | 200 Proposal, validated changes applied atomically. Same decision can be retried | 403 opt-in required, 404 unavailable, 409 expired or conflicting |
| POST `/api/coach/proposals/{id}/reject/` | Bearer, AI-enabled owner | — | — | 200 Proposal, decision stored | 403 opt-in required, 404 unavailable, 409 conflicting |

- Report periods are `weekly` (Monday through Sunday), `monthly`, and `yearly`. `date` selects the containing period and defaults to the user's current local date. Reports assign evaluated periods by their scheduled end dates. Unlogged closed periods count as failures. The percentage is successful periods divided by evaluated periods. JSON includes `period, period_start, period_end, success_count, failure_count, completion_rate, current_streak, best_streak, previous_period, completion_rate_change, challenge_performance`. Summary streaks are the maximum challenge values. The change is a difference in percentage points.
- CSV is UTF-8. The PDF language defaults to the user's locale. Persian output uses a Persian-capable font and right-to-left layout. Docker provides DejaVu Sans. For other installations, use `REPORT_PDF_FONT` to specify the font path.
- Conversation has `id, title, created_at`. Message has `id, text, reply_to, proposal_id, created_at`. A non-null `reply_to` identifies an AI response. Proposal has `id, challenge, changes, expires_at, decision, decided_at`. Proposals currently support title and description edits and expire after 24 hours.

## Internal n8n integration

All paths below start with `/api/internal/n8n/`. Configure independent high-entropy `N8N_REPORT_TOKEN` and `N8N_COACH_TOKEN` values. Configure the n8n HTTP nodes to use HTTPS and a finite request timeout. This integration uses polling so Django makes zero outbound n8n HTTP requests. Report context and Coach context deliberately omit contact details. A report delivery workflow needs a separately configured recipient mapping and provider.

| Method and path | Access | Query | JSON body | Success and function | Additional errors |
| --- | --- | --- | --- | --- | --- |
| GET `reports/users/` | Workflow, report credential | Page | — | 200 page of active opted-in users with `id,timezone,locale` | 403 invalid credential, 404 invalid page |
| GET `reports/users/{user_id}/{period}/` | Workflow, report credential | `date` | — | 200 deterministic Report context for an eligible user | 403 invalid credential, 404 ineligible or missing user |
| POST `reports/users/{user_id}/{period}/` | Workflow, report credential | — | `date,narrative` | 201 stores SmartReport. Identical retry returns 200 | 403 invalid credential, 404 ineligible or missing user, 409 different narrative for same period |
| PATCH `reports/{id}/delivery/` | Workflow, report credential | — | `status` of `delivered` or `failed` | 200 SmartReport when provider delivery succeeds | 403 invalid credential, 404 ineligible or missing report, 409 delivered report cannot revert, 502 recorded failed delivery with SmartReport body |
| GET `coach/queue/` | Workflow, Coach credential | — | — | 200 array of up to 25 pending `{id}` values for AI-enabled users | 403 invalid credential |
| GET `coach/messages/{id}/` | Workflow, Coach credential | — | — | 200 `{messages,challenges}`, with recent conversation and minimal owner challenge context | 403 invalid credential, 404 unavailable |
| POST `coach/messages/{id}/` | Workflow, Coach credential | — | `text`, optional `proposal:{challenge_id,changes:{title?,description?}}` | 201 stores a reply and optional pending proposal. Identical retry returns 200 | 403 invalid credential, 404 unavailable, 409 different reply already recorded |

A SmartReport response has `id, period, period_start, narrative, delivery_status, created_at`. The callback records the workflow's delivery outcome. Set `delivered` only after the provider confirms it. The Coach callback stores proposals. Challenge changes require the owner's explicit acceptance through the Bearer endpoint.

## Health and discovery

| Method and path | Access | Query | Body | Success and function | Additional errors |
| --- | --- | --- | --- | --- | --- |
| GET `/health/live/` | Public | — | — | 200 `{status:"ok"}` | — |
| GET `/health/ready/` | Public | — | — | 200 `{status:"ok",postgres:true,redis:true}` | 503 with dependency booleans |
| GET `/api/` | Bearer | — | — | 200 challenge router links | — |
| GET `/api/schema/` | Public | — | — | 200 OpenAPI schema | — |
| GET `/api/docs/` | Public | — | — | 200 Swagger UI HTML | — |
| GET `/api/redoc/` | Public | — | — | 200 ReDoc HTML | — |

Django's staff-only administrative interface is mounted at `/admin/`.
