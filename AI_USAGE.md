# AI Usage Disclosure

## Tool
Claude (Anthropic) in the claude.ai chat interface. No other AI tool was used.
The full prompt history is in [PROMPTS.md](PROMPTS.md).

## Approach
I used Claude as a mentor and pair programmer. I am a fresher and asked for step-by-step guidance,
so Claude drafted most of the code and I ran, tested, measured and checked it on my own machine.

## Where AI accelerated my work
- Reading the problem statement and turning it into a plan, timeline and repository structure
- Git, virtual environment and pytest setup, explained step by step
- Drafts of: the synthetic data generator, the validator, the loader, the audit tables, the audit
  report and order trace, the CLI, the test suite, the benchmark scripts and the documentation

## Where I relied on AI most heavily
- Nearly all of the source code and tests were first drafted by Claude and pasted by me.
- The design (schemas, reject reasons, reconciliation checks, idempotency by file checksum) came
  from Claude's proposals. I chose between options and approved them, but I did not invent them.
- The performance analysis: Claude read the profile output and proposed two optimisations.

## What I personally did, decided and validated
- Chose a local Python + SQLite + pytest solution rather than an Azure-hosted one, after asking
  about Azure, so that any reviewer can run the project without an account.
- Set up the environment and repository, and ran every command myself.
- Ran the test suite (27 tests passing) and the pipeline on the committed sample and on a generated
  dataset of 106,118 rows.
- Checked that counts reconcile for each file (for example customers: 5,055 read = 4,805 loaded +
  250 rejected), and confirmed that a second run of the same input skips every file.
- Ran the profiler and benchmark comparison myself and recorded the timings in DESIGN.md.
- Noticed and removed two stray screenshot files that had been pasted into the repository before
  they were committed.
- Kept the answer-key file in a separate folder from the input data.

## What I reviewed and changed
- (Add only things you really did, for example: a bug you hit and how it was fixed, a rule you
  changed, a test you added, something in the code you traced through to understand it.)

## Limitations of my AI use
- Most of the code was written by AI. I can explain the design and how each part works, but I did
  not write the first version of it myself.
- The prompt log was copied by hand from my chat history. Wording is exact, but timestamps are not
  recorded and screenshots are described rather than included.