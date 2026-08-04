# VHS tape for the README demo GIF.  https://github.com/charmbracelet/vhs
#
# Regenerate:   vhs docs/assets/demo.tape   →   docs/assets/demo.gif
#
# This drives the REAL CLI, so install it first (`sh scripts/install.sh`,
# `uv tool install verifysignal-spec`, or `pip install -e .`). To record without the proprietary runtime, point the CLI
# at the bundled fake Core:
#   export VERIFYSIGNAL_CORE_CMD="python tests/fixtures/verifysignal-core/fake_verifysignal.py"
# Then swap in a live target + real Core for the published cut.

Output docs/assets/demo.gif

Set Shell "bash"
Set FontSize 20
Set Width 1200
Set Height 720
Set Padding 24
Set Theme "Catppuccin Mocha"
Set TypingSpeed 45ms

Type "verifysignal init --here --integration claude"
Enter
Sleep 2.5s

Type "verifysignal check"
Enter
Sleep 2.5s

Type '/verifysignal "Validate that a user can sign in against https://staging.example.com"'
Enter
Sleep 1s
# The agent drafts the use case, grounds selectors against the live app,
# validates, runs deterministically, and repairs — stopping only for real unknowns.
Sleep 5s

Type "cat .verifysignal/runs/login/*/report.md"
Enter
Sleep 4s
