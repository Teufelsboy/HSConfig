# HSConfig Boarlock Fracking Source Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decide and implement the honest Boarlock `WW_092` / `Fracking` closure path without forcing weak source claims.

**Architecture:** Keep Boarlock in the existing 11-deck matrix. Add or update source documents only if exact Boarlock-relevant Fracking mulligan evidence exists; otherwise preserve the row as source-informed with an explicit stop condition and move the next closure slot to Kingslayer.

**Tech Stack:** Python 3.11+, pytest, existing HSConfig source document fixtures and source-depth reports.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Do not add dependencies.
- Do not widen the representative matrix.
- Do not promote CuteWarrior into the representative matrix.
- Do not invent a Fracking mulligan claim.
- Do not relax `SOURCE_BACKED_STRONG` promotion gates.
- Do not add post-run or HSTuner logic.

---

## First Decision

Before any fixture edit, verify whether exact Boarlock-relevant Fracking mulligan evidence exists.

- If exact evidence exists: add the atomic mulligan claim to Boarlock source documents and run source-depth closure tests.
- If exact evidence does not exist: preserve Boarlock as source-informed with explicit stop condition and prepare Kingslayer Quick Pick as the next closure candidate.
