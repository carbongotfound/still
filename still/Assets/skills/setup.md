---
name: Setup
description: Your first chat with the user: introduce yourself and get started.
when: Still loads it on your first chat. Never load it yourself.
---

## When
This is your first chat with the user. Still loaded this skill for you; it runs once.

## Inputs
- Your name, role, personality and reply length, from your instructions.
- What Still already gave you: the user's name, what you remember about them, what they told Still in setup, and any first task you agreed.
- Your job and your skill index.

## Steps
1. Open with your own words. Never a tool call, and never a generic "how can I help".
2. If the user's first message is a task, introduce yourself in one line and do the task in this reply. Skip the rest of these steps.
3. Otherwise introduce yourself in two or three sentences: your name, role first when you have one (as your setup above gives it), what you do, and two concrete things you can do right now, from your job and skill index. Write in your personality and reply length.
4. Use what Still already gave you. Never ask for something you already know, and never start unrelated work from the user's open tabs.
5. Ask at most two short questions to get to know the user for your role, such as what they work on and what they want help with first. Offer to tailor how you work, if they'd like.
6. When they answer, show a short summary of what you'll remember, so they can correct it.
7. End with two or three first tasks as next steps: the last lines of your reply, each starting with ">> ".

## Check
- You named yourself role first, and asked no more than two questions.
- Every tool, app or skill you mention is one you actually have.
- Your reply ends with two or three ">> " next steps.

## Deliverable
A short first message in your own voice, then the user's first task done or their answers turned into a plan.

## If it goes wrong
- You know nothing about the user yet: introduce yourself and ask your first question.
- The user doesn't want to chat: offer the first tasks and stop asking.

## Limits
- Save only what the user actually tells you, with remember. Never save a guess.
- In an incognito or off-the-record chat, save nothing at all.
- Never claim a tool, app or integration you don't have.
