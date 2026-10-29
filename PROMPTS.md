# Prompt History

Every prompt I sent to an AI tool while building this project, in the order I sent it, in my exact
wording (typos kept). The **Purpose** column is my own short note on what I was trying to achieve.

- **Tool:** Claude (Anthropic) via claude.ai chat. No other AI tool was used.
- **Screenshots:** several messages were screenshots only (terminal or editor output). They are listed in
  [brackets]; the images themselves are not stored in this repository.
- **Short replies:** messages that only confirmed a step ("done") are included.
- **AI responses:** omitted (optional per the FAQ).
- **Limitation:** copied by hand from my chat history, so timestamps are not recorded.

## Phase 1: Understanding the task and choosing an approach

| # | Prompt | Purpose |
|---|---|---|
| 1 | "i have a 72 hrs coding challenge i will give you the problem statemnet pls help me from end to end in that project i laso give you the gudilince of the project   this is the problem statement            and gudilince" [attached: problem statement, FAQ and submission guidelines PDFs] | Share the task and ask for end-to-end help |
| 2 | "pls tell me step by step so by tommorow evng i have to finish this tell me what i have to do from scratch like i dont know anything about this pls tell me step by step what should i do now" | Get a step-by-step plan and timeline |
| 3 | "can i craete this pipeline in Azure? like i know azure so can i create this pilplen in azurr and submit in github is that possible" | Decide the stack; I went with a local Python + SQLite build so reviewers can run it |
| 4 | "ok now spoon feed me every step how can i do i can tell u after every step did i complete or not like that" | Work through the build one verified step at a time |

## Phase 2: Environment and repository setup

| # | Prompt | Purpose |
|---|---|---|
| 5 | [screenshot: Command Prompt showing Python and Git versions] | Confirm tools; Git was missing and got installed |
| 6 | "yeah its showing 2.56.0" | Confirm Git installed |
| 7 | "what about git ignore ?" | Add a Python .gitignore when creating the repo |
| 8 | "done and username is muneer45-hub" | Confirm repository creation |
| 9 | [screenshot: git clone output] | Confirm the clone |
| 10 | "done" | Confirm Git identity setup |
| 11 | "i think in my vs code already have one so can i delete this and create or what should i do now" [screenshot: VS Code with an older project open] | Open the correct project folder instead of an old one |
| 12 | [screenshot: PowerShell execution-policy error] | Fix virtual-environment activation |
| 13 | [screenshot: pytest installed in the virtual environment] | Confirm environment setup |
| 14 | "its look good or u can give me good one to paste there" | Improve the AI-usage and prompt-log templates |
| 15 | "can i diectly paste this section or pls give me better version so recutiers get impress" | Improve the same templates |
| 16 | "ok now?" [screenshot: VS Code; prompt text pasted into README by mistake] | Fix which file the text went into |
| 17 | "prompt.md already there so this also needs to create ?" | Clarify which files to create |
| 18 | "done" | Confirm files created |
| 19 | "what is that imgs" [screenshot: git status listing two stray image files] | Understand and remove stray screenshots before committing |
| 20 | [screenshot: git status after removing the images] | Confirm the working tree was clean |
| 21 | [screenshot: GitHub repository page after the first push] | Confirm the first push |

## Phase 3: Data, pipeline and audit report

| # | Prompt | Purpose |
|---|---|---|
| 22 | "gitignore step didnt understand" | Clarify ignoring the large generated dataset |
| 23 | [screenshots: .gitignore edited in VS Code; git status output] | Confirm the ignore rule worked |
| 24 | [screenshot: GitHub page for scripts/generate_data.py] "no i already generated taht data set check once" | Confirm the data generator was pushed and the data generated |
| 25 | [screenshot: sizes and line count of the large dataset] | Confirm 100k+ generated orders |
| 26 | "what should i do now after pasted that in pyproject.toml" | Continue creating the remaining source files |
| 27 | [screenshot: VS Code] "i cnat see others on left side" | Find files inside collapsed folders |
| 28 | [screenshot: pytest, 3 passed] | Confirm the first tests passed |
| 29 | "completed now what should i do" | Move on to verifying and extending the pipeline |
| 30 | [screenshots: sample run, rerun and timing of the large run] "yeah i thinks everythig gos good" | Verify the pipeline, reruns and the large run |
| 31 | [screenshots: pytest, audit report and order trace output] | Verify the audit report and lineage trace |

## Phase 4: Performance measurement and optimisation

| # | Prompt | Purpose |
|---|---|---|
| 32 | [screenshots: baseline benchmark runs and cProfile table] | Measure first and find the bottlenecks before changing code |
| 33 | [screenshots: benchmark runs after the changes; git stash and git status output] | Check the two optimisations and that no code was lost |
| 34 | [screenshot: comparison table of the four variants] | Confirm the measured speedup (1.93x) |

## Phase 5: Documentation, checks and submission

| # | Prompt | Purpose |
|---|---|---|
| 35 | "here where i paste this" [screenshot: DESIGN.md open in VS Code] | Place the performance section in the design note |
| 36 | "done" | Confirm the design note was updated |
| 37 | [screenshot: trace_example.txt and report output] | Confirm the sample outputs |
| 38 | "this my readme where i paste this now" [README contents attached] | Fix the README after my edits |
| 39 | "done" | Confirm the README fix |
| 40 | "yesterday i closed everything and shut down the laptop so tell me now how can i continue the project and tell me how much time it still take to complete the project" | Resume the project and estimate the remaining work |
| 41 | "its ok about time the project good right ?" | Get an honest assessment of the project |
| 42 | [screenshots: git status clean, 27 tests passing, README open in VS Code] | Verify the state after resuming |
| 43 | "yeah 27 passed what next" | Continue with the final checks |
| 44 | [screenshot: GitHub repository page] | Check what was published |
| 45 | [screenshot: DESIGN.md in VS Code] "i have removed azure one so tell me next step" | Finish the design note after removing the optional Azure section |
| 46 | "i need change the prompt section the entire prompt section give me promt section like i serached like a professional" | Improve the layout of this prompt log (wording of prompts kept unchanged) |