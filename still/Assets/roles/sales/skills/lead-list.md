---
name: Lead list
description: Companies that fit who you sell to, and why each one fits.
when: Finding new leads or prospects
---

## When
The user wants new companies to sell to.

## Inputs
- Who buys: the ideal customer's industry, size, region and the signal that they need the offer. If it's empty, ask one question with ask_user and save the answer there.
- Deals, so you skip companies already in the pipeline.

## Steps
1. Turn the ideal customer into two or three searches, and run them with web_search.
2. read_url each candidate's site to confirm it fits.
3. Drop anything already in Deals or that fits only loosely.
4. For each kept company: name, website, size, why it fits in one line, and the role to contact.
5. Save the list as a CSV with save_file.

## Check
- Each "why it fits" points to something you read on their site or in the news.
- No duplicates, and nothing already in Deals.

## Deliverable
The CSV, and the best five summed up in the chat with one line each.

## If it goes wrong
- Too few matches: say how many you found and suggest widening one criterion.
- Size or region can't be confirmed: write unknown instead of estimating.

## Limits
Public information only. Name a role to contact, never a guessed person, email or phone number.
