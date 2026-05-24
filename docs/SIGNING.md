# Code signing (free, via SignPath Foundation)

The release `.exe` is unsigned by default, so Windows SmartScreen warns on download.
[SignPath Foundation](https://signpath.org/) signs **open-source** projects **for free**.
This repo is already wired for it — you just need to apply and paste 4 values.

> SignPath only signs artifacts built by a trusted CI pipeline. That's why
> [`.github/workflows/release.yml`](../.github/workflows/release.yml) builds the `.exe`
> on GitHub Actions. The signing step turns itself on once the values below exist.

## One-time setup

1. **Apply** at https://signpath.org/apply with this repository
   (`revolutedigital/haylou-s30-pro-windows`, MIT, public). Approval is manual and free.

2. After approval, in the **SignPath** dashboard:
   - Install the **SignPath GitHub App** on this repository.
   - Create a **Project** linked to the repo → note its **slug**.
   - Create a **Signing Policy** (e.g. `release-signing`) → note its **slug**.
   - Copy your **Organization ID** and create an **API token** (CI user).

3. In **GitHub → repo → Settings → Secrets and variables → Actions**:

   | Type     | Name                     | Value                         |
   |----------|--------------------------|-------------------------------|
   | Secret   | `SIGNPATH_API_TOKEN`     | the SignPath API token        |
   | Variable | `SIGNPATH_ORG_ID`        | your SignPath organization ID |
   | Variable | `SIGNPATH_PROJECT_SLUG`  | the project slug              |
   | Variable | `SIGNPATH_POLICY_SLUG`   | the signing policy slug       |

That's it. Nothing in the code changes.

## Cutting a signed release

```bash
git tag v1.2.0 && git push origin v1.2.0
```

The `Release build` workflow then: builds the `.exe` → submits it to SignPath →
attaches the **signed** binary to the GitHub release automatically.
Before SignPath is configured, the same workflow attaches the **unsigned** binary,
so releases keep working either way.

## Alternatives (if you ever want them)

- **Azure Trusted Signing** — Microsoft's own service, ~US$10/month, SmartScreen-trusted.
- **Scoop bucket** — free, no signing; power users install with `scoop install` and never
  see the SmartScreen download warning.
