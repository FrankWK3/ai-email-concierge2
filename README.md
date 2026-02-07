# AI Email Concierge

Decision-engine-first AI email concierge.

This repo is the source of truth for:
- Prompts (how the concierge thinks)
- Policies (rules + notification philosophy)
- Schema (how we log decisions now and map to automation later)

## Current approach
1. Manually sample emails
2. Classify + decide urgency/action/notify
3. Log into Excel as training data
4. Convert learned rules into policy
5. Later: connect to Outlook/Gmail + calendar + automation tools (Make/Zapier/n8n)

## Status
- v0.1: manual classification + policy build-out (in progress)
