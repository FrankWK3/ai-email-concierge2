# Approval Rules — Email Agency

This file defines what actions require explicit user approval.

## Allowed Without Approval
- Classifying emails
- Logging decisions
- Recommending actions
- Drafting replies (not sending)
- Drafting calendar events (not saving/sending)

## Requires Explicit Approval
- Sending any email
- Scheduling or modifying calendar events
- Confirming appointments with external parties
- Messaging new recipients not previously contacted

## High-Risk Actions (Never Autonomous)
- Financial decisions
- Legal or medical communications
- Sensitive personal disclosures
- Work-related communications (company policy)

## Approval Pattern
- Concierge proposes action
- User confirms with clear intent (e.g., “Send this”, “Schedule it”)
- Only then may automation execute
