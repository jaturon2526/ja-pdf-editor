<#
.SYNOPSIS
  Build JA PDF Editor images with Podman on Windows and push them to Docker Hub (on-premise tags).

.DESCRIPTION
  PowerShell version of scripts/onprem/build-push.sh for a Windows build machine with Podman Desktop / Podman for Windows.
  Run it from anywhere inside the repository (git clone).

  Tags are always separate from the public site:
    <repo>:onprem-v1.26.22-ab12cd3   pinned version (version + commit)
    <repo>:onprem                    latest on-premise build
  The script refuses "latest" and bare commit tags, which scripts/ship.sh uses for the public (ARM64) server.

  Steps: podman build (format docker, keeps HEALTHCHECK) -> smoke test + scan_eval -> push -> dist\onprem-deploy-kit.tar.gz

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\onprem\build-push.ps1
.EXAMPLE
  .\scripts\onprem\build-push.ps1 -Target backend -NoPush
.EXAMPLE
  .\scripts\onprem\build-push.ps1 -Platform linux/arm64
.EXAMPLE
  .\scripts\onprem\build-push.ps1 -Target kit
#>
[CmdletBinding()]
param(
  # all | backend | frontend | kit | tags
  [ValidateSet("all", "backend", "frontend", "kit", "tags")]
  [string]$Target = "all",
  # Target server architecture: linux/amd64 (default) | linux/arm64 | "linux/amd64,linux/arm64" (multi-arch manifest)
  [string]$Platform,
  # Custom tag instead of onprem-v<version>-<commit>
  [string]$Tag,
  [string]$BackendImage,
  [string]$FrontendImage,
  [string]$TagPrefix,
  [switch]$NoPush,      # build + test only
  [switch]$SkipEval,    # skip scan_eval / thai_eval
  [switch]$NoCache,     # rebuild every layer
  [switch]$GitPull,     # git pull --ff-only first
  [switch]$AllowDirty,  # allow uncommitted changes (tag gets -dirty)
  [switch]$Yes,         # do not ask for confirmation
  [switch]$DryRun       # print commands only
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

# ---------- helpers ----------
function Step([string]$m) { Write-Host "==> $m" -ForegroundColor Cyan }
function Ok([string]$m)   { Write-Host "OK  $m" -ForegroundColor Green }
function Warn([string]$m) { Write-Host "!   $m" -ForegroundColor Yellow }
function Die([string]$m)  { Write-Host "X   $m" -ForegroundColor Red; exit 1 }

# Run an external command; stop on a non-zero exit code. -DryRun only prints it.
# Arguments avoid embedded double quotes: Windows PowerShell 5.1 passes them to native programs incorrectly.
function Run {
  param([Parameter(Mandatory)][string]$Exe, [string[]]$Arguments = @(), [string]$OnError)
  $shown = ($Arguments | ForEach-Object { if ($_ -match '\s') { '"' + $_ + '"' } else { $_ } }) -join ' '
  if ($DryRun) { Write-Host "   [dry-run] $Exe $shown"; return }
  & $Exe @Arguments
  if ($LASTEXITCODE -ne 0) {
    if ($OnError) { Die $OnError } else { Die "$Exe $shown (exit $LASTEXITCODE)" }
  }
}

function Confirm-Step([string]$question) {
  if ($Yes) { return $true }
  $a = Read-Host "$question [y/N]"
  return ($a -match '^[Yy]$')
}

# ---------- repository + settings ----------
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Die "git not found - install Git for Windows (https://git-scm.com/download/win)" }
$Root = (& git rev-parse --show-toplevel 2>$null)
if ($LASTEXITCODE -ne 0 -or -not $Root) { Die "Run this inside the repository folder (git clone)" }
$Root = $Root.Trim()
Set-Location $Root

# Optional settings shared with build-push.sh: scripts/onprem/build.env (KEY=VALUE, not in git)
$Conf = @{}
$ConfPath = Join-Path $Root "scripts/onprem/build.env"
if (Test-Path $ConfPath) {
  foreach ($line in Get-Content $ConfPath -Encoding UTF8) {
    if ($line -match '^\s*([A-Z_]+)\s*=\s*(.*?)\s*$') { $Conf[$Matches[1]] = $Matches[2].Trim('"').Trim("'") }
  }
}
function Setting([string]$value, [string]$key, [string]$default) {
  if ($value) { return $value }
  if ($Conf.ContainsKey($key) -and $Conf[$key]) { return $Conf[$key] }
  $envValue = [Environment]::GetEnvironmentVariable($key)
  if ($envValue) { return $envValue }
  return $default
}
$Platform      = Setting $Platform      "PLATFORM"       "linux/amd64"
$BackendImage  = Setting $BackendImage  "BACKEND_IMAGE"  "docker.io/jaturon2526/pdf-editor-backend"
$FrontendImage = Setting $FrontendImage "FRONTEND_IMAGE" "docker.io/jaturon2526/pdf-editor-frontend"
$TagPrefix     = Setting $TagPrefix     "TAG_PREFIX"     "onprem"
$Tag           = Setting $Tag           "TAG"            ""
$Corpus = Join-Path $Root "test_pdf_files"
$Dist = Join-Path $Root "dist"
$LastTagFile = Join-Path $Root "scripts/onprem/.last-tag"

function Image-Of([string]$svc) { if ($svc -eq "backend") { $BackendImage } else { $FrontendImage } }

function App-Version {
  $about = Join-Path $Root "frontend/src/components/AboutModal.jsx"
  $m = Select-String -Path $about -Pattern '>v(\d+\.\d+\.\d+)<' -Encoding UTF8 | Select-Object -First 1
  if ($m) { return "v" + $m.Matches[0].Groups[1].Value }
  return "v0.0.0"
}

function Check-Tag([string]$t) {
  if ($t -notmatch '^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$') { Die "Tag '$t' is not valid (A-Z a-z 0-9 _ . -, max 128)" }
  if ($t -eq "latest") { Die "Tag 'latest' belongs to the public site (scripts/ship.sh) - use the onprem tags" }
  if ($t -match '^[0-9a-f]{7,40}$') { Die "A bare commit tag collides with the public site's rollback tags" }
}

function Test-Podman {
  if (-not (Get-Command podman -ErrorAction SilentlyContinue)) {
    Die "podman not found - install Podman Desktop / Podman for Windows (https://podman.io), then: podman machine init; podman machine start"
  }
  & podman info *> $null
  if ($LASTEXITCODE -ne 0) {
    Die "Cannot reach the Podman machine - start it: podman machine start  (first time: podman machine init)"
  }
}

function Is-Dirty {
  $s = (& git status --porcelain --untracked-files=no)
  return [bool]($s)
}

# ---------- build + push ----------
function Build-Push([string]$what) {
  $svcs = if ($what -eq "all") { @("backend", "frontend") } else { @($what) }
  Test-Podman

  $autocrlf = (& git config --get core.autocrlf)
  if ($autocrlf -eq "true") {
    Warn "git core.autocrlf=true - files are checked out with CRLF. Images still work, but a clean LF checkout is safer:"
    Warn "  git config core.autocrlf input; git rm -r --cached -q .; git reset --hard"
  }

  if ($GitPull) {
    Step "git pull"
    Run git @("pull", "-q", "--ff-only") -OnError "git pull failed"
  }
  if (Is-Dirty) {
    & git status --short --untracked-files=no
    if (-not $AllowDirty) { Die "Uncommitted changes - commit/stash them first, or use -AllowDirty (tag gets -dirty)" }
  }

  $sha = (& git rev-parse --short=7 HEAD).Trim()
  $fullSha = (& git rev-parse HEAD).Trim()
  $subject = (& git log -1 --format=%s).Trim()
  $version = App-Version
  $dirty = if (Is-Dirty) { "-dirty" } else { "" }
  $tag = if ($Tag) { $Tag } else { "$TagPrefix-$version-$sha$dirty" }
  Check-Tag $tag
  Check-Tag $TagPrefix

  $multi = $Platform.Contains(",")
  if ($multi -and $NoPush) { Die "Multi-arch ($Platform) builds a manifest that is pushed directly - -NoPush is not supported" }
  if ($Platform -ne "linux/amd64") {
    Warn "Building $Platform on an x86_64 Podman machine needs QEMU emulation (slow):"
    Warn "  podman machine ssh sudo rpm-ostree install qemu-user-static; podman machine stop; podman machine start"
  }

  Write-Host "Build: $($svcs -join ' ')  -  commit $sha ($subject)"
  Write-Host "  platform: $Platform  -  tags: $tag and $TagPrefix"
  foreach ($s in $svcs) { Write-Host "  $(Image-Of $s):$tag" }
  if ($NoPush) { Write-Host "  (-NoPush: not pushing)" }
  if (-not (Confirm-Step "Continue?")) { Die "Cancelled" }

  # --format docker: OCI images drop HEALTHCHECK, and deploy.sh waits for the backend health check
  $common = @("--format", "docker",
    "--label", "org.opencontainers.image.revision=$fullSha",
    "--label", "org.opencontainers.image.version=$version",
    "--label", "org.opencontainers.image.created=$((Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'))",
    "--label", "ja.pdf-editor.channel=$TagPrefix")
  if ($NoCache) { $common += "--no-cache" }

  if ($multi) {
    Warn "Multi-arch: no local smoke test (test one platform first with -NoPush -Platform linux/amd64)"
    foreach ($s in $svcs) {
      $img = Image-Of $s
      $manifest = "localhost/pdf-editor-$s-manifest:$tag"
      Step "build $s ($Platform) -> manifest"
      & podman manifest rm $manifest *> $null
      Run podman (@("build", "--platform", $Platform, "--manifest", $manifest) + $common + @((Join-Path $Root $s)))
      Step "push $img`:$tag and :$TagPrefix"
      Run podman @("manifest", "push", "--all", $manifest, "docker://$img`:$tag") -OnError "Push failed - did you run: podman login docker.io ?"
      Run podman @("manifest", "push", "--all", $manifest, "docker://$img`:$TagPrefix")
    }
  } else {
    foreach ($s in $svcs) {
      $img = Image-Of $s
      Step "build $s ($Platform)"
      Run podman (@("build", "--platform", $Platform, "-t", "$img`:$tag") + $common + @((Join-Path $Root $s)))
      Run podman @("tag", "$img`:$tag", "$img`:$TagPrefix")
    }
    Smoke-Test $svcs $tag
    if (-not $NoPush) {
      foreach ($s in $svcs) {
        $img = Image-Of $s
        Step "push $img`:$tag and :$TagPrefix"
        Run podman @("push", "--format", "v2s2", "$img`:$tag") -OnError "Push failed - did you run: podman login docker.io ?  (the account needs write access to this repository)"
        Run podman @("push", "--format", "v2s2", "$img`:$TagPrefix")
      }
    }
  }

  if (-not $DryRun) { Set-Content -Path $LastTagFile -Value $tag -Encoding ASCII }
  Make-Kit $tag
  Ok "Done: tag $tag"
  if (-not $NoPush) {
    Write-Host ""
    Write-Host "On the on-premise server:"
    Write-Host "  ./deploy.sh deploy $tag        (or ./deploy.sh deploy $TagPrefix = always the latest)"
    if ($svcs.Count -lt 2) { Warn "Only $($svcs -join ' ') was built - tag $tag does not exist for the other image; deploy with $TagPrefix instead" }
  }
}

function Smoke-Test([string[]]$svcs, [string]$tag) {
  if ($svcs -contains "backend") {
    Step "test backend: core libraries + Ghostscript / LibreOffice / Tesseract (tha)"
    Run podman @("run", "--rm", "$BackendImage`:$tag", "sh", "-c",
      "python -c 'import fitz, pikepdf, pyhanko, fpdf, app.main' && gs --version && soffice --version >/dev/null && tesseract --list-langs 2>/dev/null | grep -q tha") `
      -OnError "Backend image is broken - not pushed"
    if ($SkipEval) {
      Warn "-SkipEval: skipping evaluation suites"
    } else {
      Step "scan_eval (scanned PDF -> Word, synthetic documents)"
      Run podman @("run", "--rm", "$BackendImage`:$tag", "python", "-m", "scripts.scan_eval", "--check") `
        -OnError "scan_eval failed - not pushed (skip with -SkipEval if you are sure)"
      if (Test-Path $Corpus) {
        Step "thai_eval with test_pdf_files\"
        Run podman @("run", "--rm", "-v", "${Corpus}:/corpus:ro", "$BackendImage`:$tag", "python", "-m", "scripts.thai_eval", "/corpus", "--check") `
          -OnError "thai_eval failed - not pushed"
      }
    }
  }
  if ($svcs -contains "frontend") {
    Step "test frontend: web app + manual present"
    Run podman @("run", "--rm", "--entrypoint", "sh", "$FrontendImage`:$tag", "-c",
      "test -s /usr/share/nginx/html/index.html && test -s /usr/share/nginx/html/manual.html") `
      -OnError "Frontend image is incomplete - not pushed"
  }
}

# ---------- deploy kit for the server (no source code needed there) ----------
# Text files are written with LF endings: a CRLF deploy.sh / .env breaks on Linux.
function Write-Lf([string]$src, [string]$dst, [scriptblock]$transform) {
  $text = [System.IO.File]::ReadAllText($src, [System.Text.Encoding]::UTF8)
  $text = $text -replace "`r`n", "`n"
  if ($transform) { $text = & $transform $text }
  $dir = Split-Path $dst -Parent
  if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
  [System.IO.File]::WriteAllText($dst, $text, (New-Object System.Text.UTF8Encoding($false)))
}

function Make-Kit([string]$tag) {
  if (-not $tag) {
    if (Test-Path $LastTagFile) { $tag = (Get-Content $LastTagFile -Raw).Trim() } else { $tag = $TagPrefix }
  }
  Step "deploy kit"
  $out = Join-Path $Dist "onprem-deploy-kit.tar.gz"
  if ($DryRun) { Write-Host "   [dry-run] $out"; return }
  if (-not (Get-Command tar -ErrorAction SilentlyContinue)) { Die "tar not found (Windows 10 1803+ includes tar.exe)" }
  New-Item -ItemType Directory -Path $Dist -Force | Out-Null
  $tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("pdf-kit-" + [guid]::NewGuid().ToString("N"))
  $kit = Join-Path $tmp "pdf-editor"
  try {
    Write-Lf (Join-Path $Root "docker-compose.prod.yml") (Join-Path $kit "docker-compose.prod.yml") $null
    Write-Lf (Join-Path $Root "docker-compose.onprem-tls.yml") (Join-Path $kit "docker-compose.onprem-tls.yml") $null
    Write-Lf (Join-Path $Root "deploy/onprem/nginx-tls.conf") (Join-Path $kit "deploy/onprem/nginx-tls.conf") $null
    Write-Lf (Join-Path $Root "scripts/onprem/deploy.sh") (Join-Path $kit "deploy.sh") $null
    $b = $BackendImage; $f = $FrontendImage
    Write-Lf (Join-Path $Root ".env.onprem.template") (Join-Path $kit ".env.onprem.template") {
      param($t)
      $t = $t -replace '(?m)^IMAGE_TAG=.*$', "IMAGE_TAG=$tag"
      $t = $t -replace '(?m)^BACKEND_IMAGE=.*$', "BACKEND_IMAGE=$b"
      $t -replace '(?m)^FRONTEND_IMAGE=.*$', "FRONTEND_IMAGE=$f"
    }
    $short = (& git rev-parse --short=7 HEAD).Trim()
    $readme = @"
JA PDF Editor - on-premise deploy kit
images: $BackendImage / $FrontendImage  tag: $tag
built from commit $short on $((Get-Date).ToString('yyyy-MM-dd HH:mm')) (Windows / Podman)

1. tar xzf onprem-deploy-kit.tar.gz && cd pdf-editor
2. bash deploy.sh setup      check the server + create .env.prod from the template -> edit the <...> values
   (files packed on Windows lose the executable bit: chmod +x deploy.sh to run it as ./deploy.sh)
3. put secrets in ./secrets  (tls/fullchain.pem, tls/privkey.pem, seal.p12 ...) - see .env.prod
4. bash deploy.sh deploy     pull the images for the tag in .env.prod and start
More: bash deploy.sh help
Full guide: README.md in the repository, on-premise section (On-premise)
"@
    [System.IO.File]::WriteAllText((Join-Path $kit "README.txt"), ($readme -replace "`r`n", "`n"), (New-Object System.Text.UTF8Encoding($false)))
    if (Test-Path $out) { Remove-Item $out -Force }
    & tar -czf $out -C $tmp "pdf-editor"
    if ($LASTEXITCODE -ne 0) { Die "tar failed" }
  } finally {
    if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
  }
  Ok "Kit: $out  (copy to the server: scp `"$out`" user@server:~/)"
}

function List-Tags {
  Test-Podman
  $rows = & podman images --format "{{.Repository}}:{{.Tag}}`t{{.CreatedSince}}`t{{.Size}}"
  $hits = $rows | Where-Object { $_ -match "^(?:docker\.io/)?(?:$([regex]::Escape($BackendImage -replace '^docker\.io/', ''))|$([regex]::Escape($FrontendImage -replace '^docker\.io/', ''))):$([regex]::Escape($TagPrefix))" }
  if ($hits) { $hits } else { Write-Host "(no $TagPrefix tags on this machine)" }
}

switch ($Target) {
  "kit"  { Make-Kit "" }
  "tags" { List-Tags }
  default { Build-Push $Target }
}
