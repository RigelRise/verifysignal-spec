# Quickstart: Hermetic Update and Test Readiness

## Use a released Core

```bash
verifysignal core update --json
verifysignal core version --json
```

The update exits development override mode and selects the latest verified
managed release. To remove local resolution without contacting the backend:

```bash
verifysignal core reset --json
```

## Confirm the test target

When VerifySignal recommends a URL, confirm it or provide another one in the
workflow clarification. A recommendation found in the repository is not
authorization to browse or run against it.

## Prepare declared test credentials

After the use case reports exact missing keys and after you approve file
creation:

```bash
verifysignal credentials prepare create-project \
  --env-file .env.verifysignal.test.local \
  --json
```

Fill the empty assignments locally, then use the file explicitly:

```bash
verifysignal validate create-project --runtime-readiness \
  --env-file .env.verifysignal.test.local --json
verifysignal probe --run .verifysignal/run-requests/create-project.yaml \
  --skill .verifysignal/skills/create-project.browser.md \
  --env-file .env.verifysignal.test.local --json
verifysignal run create-project \
  --env-file .env.verifysignal.test.local --json
```

Do not source the file. VerifySignal parses a strict non-executable subset and
passes only declared keys to the Core child process.
