# Siftelo 0.1.0 beta candidate: feedback instructions

Thank you for testing Siftelo. Feedback is most useful when it is specific and when it is safe to share.

## Where to send feedback

Use **GitHub Issues** on this repository for non-sensitive feedback and bug reports. Do not put repository
contents, secrets or personal data in an issue (see "What not to send" below).

For a private beta, the owner may agree a separate private channel with each tester. Use that channel only if you
were given it. Security problems are not feedback: see `SECURITY.md`.

## What to send

Answer what you can. Short answers are fine.

1. Which handoff format did you test with, and did Siftelo understand it?
2. Which finding surprised you most: a false `stale`, a missing `stale`, or an `unknown` that should have
   been resolved?
3. Did a blocker marker (`Blocked:` / `Blocker:`) get counted when it should not, or ignored when it should
   have been counted?
4. Was the exit code meaningful in your CI or script? What would you have needed instead?
5. Which step in the installation or quick start was unclear, and where did you get stuck?
6. Did the report expose anything you would not want in a log, a ticket or a chat message?
7. What is the one thing you would change first?
8. Which operating system, Python version and Git version did you use?

## What not to send

- Repository contents, source code, or the handoff itself, unless you have a synthetic copy.
- Secrets, tokens, passwords, private URLs, customer or personal data.
- A raw report from a private repository. Redact it first (see `PRIVACY.md`, section 5), or describe the
  finding in your own words.
- Security problems. Report those as described in `SECURITY.md`, not as general feedback.

## Reproduce with a synthetic example

If you can, reproduce the issue with a small synthetic repository:

```powershell
git init -b main synthetic
cd synthetic
git -c user.name=Test -c user.email=test@example.invalid commit --allow-empty -m "synthetic"
```

Then put a handoff that shows the problem beside it, and run Siftelo on that folder. A synthetic example can be
shared in full.

## Feedback template

```markdown
Siftelo version: 0.1.0 (beta candidate)
Install route: source tree / wheel / other
OS and version:
Python version:
Git version:
Command run (paths redacted):
Exit code received:
Exit code expected, and why:
What happened:
What you expected:
Synthetic reproduction (attach or describe):
Redacted report excerpt (optional):
```
