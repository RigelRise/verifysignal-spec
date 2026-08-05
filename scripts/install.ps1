#Requires -Version 5.1
<#
.SYNOPSIS
    Bootstrap installer for the VerifySignal CLI on Windows.

.DESCRIPTION
    The documented one-line install used to be `uv tool install verifysignal-spec`, which silently
    assumes the reader already has uv — and most first-time readers do not. They hit
    "uv is not recognized" on step 01 of onboarding, with no in-product way forward. This script is
    the missing step: it installs uv when it is absent, and uv in turn downloads a managed Python
    3.11+ when the machine has none. Windows Powershell 5.1 (shipped with the OS) is enough.

    When npm is present it also pre-installs the pinned Playwright MCP provider, which is what
    gives the agent its browser tools. `verifysignal init` installs that provider too, so this is a
    pre-warm rather than the only chance - what it buys is TIMING: a machine with no Node otherwise
    installs cleanly here, comes back blocked at `init`, and starts its first agent session with no
    browser tooling at all.

    What it deliberately does NOT do: install Node.js or Chromium. An installer that reaches for a
    package manager to satisfy a runtime dependency is an installer that fails on the machines it
    was written to help. It warns instead, and names the command that fixes each gap.

    This is the Windows twin of scripts/install.sh; keep the two in step.

.PARAMETER Version
    Install an exact release from PyPI instead of the latest.

.PARAMETER From
    Install from an arbitrary source (e.g. a git+https URL) instead of PyPI.

.PARAMETER NoModifyPath
    Do not let uv touch the user PATH environment variable.

.PARAMETER SkipPlaywrightMcp
    Do not pre-install the Playwright MCP provider (offline installs, CI).

.EXAMPLE
    powershell -ExecutionPolicy Bypass -c "irm https://verifysignal.io/install.ps1 | iex"

.EXAMPLE
    .\install.ps1 -Version 0.26.0
#>
[CmdletBinding()]
param(
    [string]$Version = $env:VERIFYSIGNAL_INSTALL_VERSION,
    [string]$From = $env:VERIFYSIGNAL_INSTALL_FROM,
    [switch]$NoModifyPath,
    [switch]$SkipPlaywrightMcp
)

$ErrorActionPreference = 'Stop'

$Package = 'verifysignal'
$LegacyPackage = 'verifysignal-spec'
# The interpreter the CLI runs on. Pinned rather than left to whatever Python the machine has, so
# that the install is identical on a machine with 3.9, a machine with 3.13, and a machine with none.
$PythonVersion = '3.12'
$UvInstallerUrl = 'https://astral.sh/uv/install.ps1'
$PlaywrightMcpSetup = 'verifysignal integration setup-playwright-mcp'
$DocsUrl = 'https://github.com/RigelRise/verifysignal/blob/main/docs/installation.md'

# Windows PowerShell 5.1 still negotiates SSLv3/TLS1.0 by default on older builds, and both
# astral.sh and PyPI refuse those. Without this the download fails with an opaque "could not create
# SSL/TLS secure channel".
try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
} catch {
    # .NET (Core) on PowerShell 7+ manages this itself and may not expose the property.
}

function Write-Step { param([string]$Message) Write-Host "==> $Message" -ForegroundColor Cyan }
function Write-Note { param([string]$Message) Write-Host "    $Message" }
function Write-Warn { param([string]$Message) Write-Warning $Message }
# Write-Host + exit rather than Write-Error: with $ErrorActionPreference = 'Stop' a Write-Error is a
# terminating exception, so the exit code the caller sees would be the host's, not ours.
function Stop-WithError { param([string]$Message) Write-Host "error: $Message" -ForegroundColor Red; exit 1 }

if ($Version -and $From) {
    Stop-WithError 'Version and From are mutually exclusive: pin the version inside the From spec instead.'
}

if ($env:VERIFYSIGNAL_NO_MODIFY_PATH) {
    $NoModifyPath = $true
}

if ($env:VERIFYSIGNAL_SKIP_PLAYWRIGHT_MCP) {
    $SkipPlaywrightMcp = $true
}

# --- resolve uv ---------------------------------------------------------------------------------
# uv installs itself to %USERPROFILE%\.local\bin, which is not on PATH in the session that runs this
# script. So Get-Command alone is not enough: check the known install locations before deciding uv
# is missing, and again after installing it.
function Resolve-Uv {
    $onPath = Get-Command uv -ErrorAction SilentlyContinue
    if ($onPath) { return $onPath.Source }

    $candidates = @(
        (Join-Path $env:USERPROFILE '.local\bin\uv.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\uv\uv.exe'),
        (Join-Path $env:USERPROFILE '.cargo\bin\uv.exe')
    )
    if ($env:UV_INSTALL_DIR) {
        $candidates = , (Join-Path $env:UV_INSTALL_DIR 'uv.exe') + $candidates
    }

    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate -PathType Leaf)) { return $candidate }
    }
    return $null
}

$uv = Resolve-Uv

if (-not $uv) {
    Write-Step 'uv not found - installing it from astral.sh'
    # Piping the vendor installer is the documented, signed-release path for uv. We do not mirror or
    # re-host it: a stale copy of someone else's installer is worse than the original.
    try {
        Invoke-RestMethod -UseBasicParsing $UvInstallerUrl | Invoke-Expression
    } catch {
        Stop-WithError "The uv installer failed: $($_.Exception.Message). Install uv manually (https://docs.astral.sh/uv/getting-started/installation/) and re-run this script."
    }

    # The installer edits the persisted user PATH; it cannot change THIS session. Make its default
    # location visible so the resolve below succeeds without opening a new terminal.
    $uvDir = if ($env:UV_INSTALL_DIR) { $env:UV_INSTALL_DIR } else { Join-Path $env:USERPROFILE '.local\bin' }
    $env:Path = "$uvDir;$env:Path"

    $uv = Resolve-Uv
    if (-not $uv) {
        Stop-WithError "uv still not found after installation. Open a new terminal and re-run, or install uv manually. See $DocsUrl"
    }
    Write-Note "uv installed at $uv"
} else {
    Write-Note "using uv at $uv"
}

# --- install the CLI ----------------------------------------------------------------------------
# uv registers tools by distribution name. The legacy and canonical distributions expose the same
# executables and import package, so replace the legacy tool before installing the canonical one.
$installedTools = (& $uv tool list 2>$null | Out-String)
$legacyPattern = "(?m)^$([regex]::Escape($LegacyPackage))(?:\s|$)"
if ($installedTools -match $legacyPattern) {
    Write-Step "Replacing legacy $LegacyPackage installation"
    & $uv tool uninstall $LegacyPackage
    if ($LASTEXITCODE -ne 0) {
        Stop-WithError "Could not remove the legacy $LegacyPackage tool. Remove it manually, then re-run."
    }
}

# --force makes re-running the one-liner an upgrade rather than a no-op, which is what a user who
# pastes the install command a second time actually means.
$uvArgs = @('tool', 'install', '--force', '--python', $PythonVersion)

if ($From) {
    Write-Step "Installing $Package from $From"
    $uvArgs += @($Package, '--from', $From)
} elseif ($Version) {
    Write-Step "Installing $Package==$Version"
    $uvArgs += "$Package==$Version"
} else {
    Write-Step "Installing $Package"
    $uvArgs += $Package
}

& $uv @uvArgs
if ($LASTEXITCODE -ne 0) {
    Stop-WithError "Installation failed (uv exited with $LASTEXITCODE). Re-run the same command to retry, or see $DocsUrl"
}

if (-not $NoModifyPath) {
    # Best effort: a PATH entry uv cannot persist is not a reason to fail an otherwise complete
    # install - the directory is printed below either way.
    & $uv tool update-shell *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Warn 'Could not update PATH automatically; add the directory printed below to PATH yourself.'
    }
}

# --- verify -------------------------------------------------------------------------------------
$toolDir = (& $uv tool dir --bin 2>$null | Select-Object -First 1)
if (-not $toolDir) { $toolDir = Join-Path $env:USERPROFILE '.local\bin' }

$verifysignal = Join-Path $toolDir 'verifysignal.exe'
if (-not (Test-Path -LiteralPath $verifysignal -PathType Leaf)) {
    $onPath = Get-Command verifysignal -ErrorAction SilentlyContinue
    if ($onPath) { $verifysignal = $onPath.Source } else { $verifysignal = $null }
}
if (-not $verifysignal) {
    Stop-WithError "Installed, but the verifysignal executable was not found under $toolDir. See $DocsUrl"
}

$installedVersion = (& $verifysignal --version 2>&1 | Out-String).Trim()
if ($LASTEXITCODE -ne 0) {
    Stop-WithError "The installed verifysignal binary failed to run: $installedVersion"
}

Write-Host ''
Write-Host "OK $installedVersion" -ForegroundColor Green

# --- browser tooling ------------------------------------------------------------------------------
# See scripts/install.sh for why this runs here: `verifysignal init` installs the same provider, but
# a machine with no Node only finds that out mid-onboarding, after `init` comes back blocked and the
# first agent session has no browser tools. The provider lands in a user cache, so this is a cache
# hit on a re-run.
$node = Get-Command node -ErrorAction SilentlyContinue
if ($node) {
    $nodeVersion = (& node --version 2>$null | Out-String).Trim()
    if ($nodeVersion -match '^v(\d+)') {
        if ([int]$Matches[1] -lt 24) {
            Write-Warn "Node.js $nodeVersion found; VerifySignal needs Node.js 24+ to run validations."
        }
    } else {
        Write-Warn 'Could not read the Node.js version; VerifySignal needs Node.js 24+.'
    }
} else {
    Write-Warn 'Node.js not found; VerifySignal needs Node.js 24+ to run validations.'
}

if ($SkipPlaywrightMcp) {
    Write-Note 'Skipping Playwright MCP setup (-SkipPlaywrightMcp).'
} elseif (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Write-Warn "npm not found, so the Playwright MCP provider was not installed. Install Node.js 24+, then run: $PlaywrightMcpSetup - until then ``verifysignal init`` cannot set up browser tooling and the agent starts without it."
} else {
    Write-Step 'Installing the pinned Playwright MCP provider (this can take a minute)'
    # Non-fatal by design: the CLI is installed and useful, and this step depends on the npm
    # registry. Failing the whole install over a provider that `init` will retry is the wrong trade.
    & $verifysignal integration setup-playwright-mcp *> $null
    if ($LASTEXITCODE -eq 0) {
        Write-Note 'Browser tooling ready.'
    } else {
        Write-Warn "Could not install the Playwright MCP provider. Retry with: $PlaywrightMcpSetup"
    }
}

Write-Host ''
Write-Host 'Next steps:'
if (($env:Path -split ';') -notcontains $toolDir.TrimEnd('\')) {
    Write-Host "  0. Open a new terminal (or add $toolDir to PATH) so 'verifysignal' resolves."
}
Write-Host '  1. cd into your project'
Write-Host '  2. verifysignal init --here --integration claude   # or: codex'
Write-Host '  3. verifysignal check                              # workspace and Core runtime readiness'
