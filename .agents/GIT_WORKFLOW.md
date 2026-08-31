# Git Workflow Rules — Linear History (STRICT)

These rules apply to **every repo** and **every branch/phase**. Follow them exactly, in order. Do not skip, reorder, or "helpfully" substitute a different git command (e.g. never use `git merge`, never use `git pull` without `--rebase`, never use plain `git rebase <branch>` on `development`).

Core principle: `development` is **always** a fast-forward mirror of `origin/development`. It never has local-only commits, and it is never rebased *onto* a feature branch. All divergence is resolved by feature branches rebasing onto `development` — never the other way around.

---

## Trigger: "create a branch for [phase/feature]"

Run, in order:

```bash
git checkout development
git fetch origin
git reset --hard origin/development
git checkout -b feature/<phase-name>
```

Then implement the work (code, tests) and commit normally:

```bash
git add .
git commit -m "feat(scope): description"
```

Commit as many times as needed during the work. Use clear, conventional commit messages.

## Trigger: "push this branch" / work on the phase is complete

Before the final push, always rebase onto the latest `development`:

```bash
git fetch origin
git rebase origin/development
```

- If there are conflicts, resolve them, then `git rebase --continue`.
- Once the rebase is clean, push:

```bash
git push -u origin feature/<phase-name>
```

- If the branch was already pushed before and history was rewritten by the rebase, push with `--force-with-lease` instead of `-f`:

```bash
git push --force-with-lease origin feature/<phase-name>
```

**After pushing, STOP and tell the user:**
> "Branch pushed. Please open the PR on GitHub and use **Rebase and Merge**. Let me know once that's done."

Do not proceed further. Do not merge locally. Do not touch `development`. Wait for the user's explicit confirmation (e.g. "rebase and merge done" / "completed").

## Trigger: user confirms the PR was rebase-and-merged on GitHub

Run, in order:

```bash
git checkout development
git fetch origin
git reset --hard origin/development
```

This realigns local `development` with the new commit GitHub created during the rebase-merge, keeping the graph linear. The old local feature branch can be deleted at this point:

```bash
git branch -D feature/<phase-name>
```

The repo is now ready for the next phase — go back to the first trigger above.

---

## Hard rules — never do these

- ❌ Never run `git rebase origin/feature/...` (or any feature branch) **onto `development`**. Rebasing always goes feature → development, never the reverse.
- ❌ Never `git merge` anything into `development` locally.
- ❌ Never `git pull` (plain) on `development` — it merges. Always `fetch` + `reset --hard origin/development`.
- ❌ Never merge a PR yourself or click merge buttons other than "Rebase and Merge" — that's the user's manual step on GitHub.
- ❌ Never force-push `development`.
- ❌ Never skip the pre-push rebase (`git rebase origin/development`) on a feature branch before pushing.

## Quick reference

| Trigger | Commands |
|---|---|
| Start new phase | checkout dev → fetch → reset --hard → checkout -b feature/... |
| Before pushing | fetch → rebase origin/development → push (force-with-lease if re-pushing) |
| After push | **stop**, ask user to Rebase and Merge on GitHub |
| After user confirms merge | checkout dev → fetch → reset --hard origin/development → delete local feature branch |
