# Research note: Windows code signing, SmartScreen, and OSS distribution

> **Status:** Research / decision input. Settles the "code signing budget item" question in the [roadmap](../roadmap.md) V1 list and feeds the pending Beta-installable amendment.
> **Date:** 2026-07-05
> **Method:** web research (CA offerings, Microsoft documentation, OSS community practice), not a spike — there is nothing to run. Prices and Microsoft policy drift; re-verify the table before acting on it if much time has passed.
> **Scope:** trust UX for distributing the Takki `.exe`/installer (Beta pilot bundle and V1 public release). Not about the PyInstaller build itself.

## The one-line finding

**Paying for a code-signing certificate buys Takki nothing it needs.** Since ~2024 SmartScreen grants no instant reputation to any certificate class — even EV — so a signed Beta downloaded by 3–5 pilot families shows the same "unrecognized app" wall as an unsigned one, just with a nicer publisher line. Reputation comes from *download volume* under a stable identity, which a hobby project accrues via free channels: unsigned + documented click-through (Beta), SignPath Foundation signatures (from first public release), and the Microsoft Store ($19 one-time, Microsoft-signed, **never** shows SmartScreen) as the V1 endgame. Total out-of-pocket across the whole roadmap: **$19**.

## SmartScreen mechanics (the facts that drive everything)

- SmartScreen reputation is earned per-identity by clean-download volume — Microsoft's guidance says weeks and *hundreds of clean installs from a wide audience*. There is no purchasable shortcut anymore: the old "EV = instant reputation" rule was dropped (~2024); OV and EV now build reputation the same way.
- **Unsigned** files build reputation **per file hash** — it resets on every release. **Signed** files build it **per publisher identity** — it carries across releases and builds faster on a renewed/known certificate. This is the only real long-term value of signing for a small project: continuity of identity, not removal of the first-contact warning.
- The **Microsoft Store** sidesteps SmartScreen entirely: Microsoft re-signs the package, users never see a warning, and there is no certificate to buy or renew. Individual developer registration is $19 one-time.
- Package-manager installs (**winget**, Scoop, Chocolatey) don't go through the browser download flow (no Mark-of-the-Web), so the SmartScreen dialog doesn't appear. Bonus for this project: `winget install` in a terminal is fully keyboard/screen-reader accessible — arguably friendlier to a VI parent than a GUI click-through dance.

## Options evaluated (verified 2026-07-05)

| Route | Cost | Effort / bureaucracy | Verdict for Takki |
|---|---|---|---|
| **Ship unsigned**, document the click-through | €0 | One paragraph in the install instructions | ✅ Beta. Pilot families are known people; trust is interpersonal. This is the dominant hobby-OSS practice. |
| **SignPath Foundation** (free OSS signing) | €0 | Application + review (weeks); sign via their pipeline hooked to GitHub Actions; manual approval per release; requires an already-published release; publisher reads "SignPath Foundation" | ✅ Apply at first public release. Starts the reputation clock under a stable identity for free. |
| **Microsoft Store** (MSIX, store-signed) | $19 one-time | MSIX packaging + store review; must verify pynput's global hook under `runFullTrust` | ✅ V1 endgame — the only zero-warning path, and the most audience-appropriate channel (non-technical parents, school IT allows Store). |
| **winget manifest** | €0 | Manifest PR to `winget-pkgs`; hash-pinned per release | ✅ V1 secondary channel; screen-reader-friendly install path. |
| **Certum Open Source cert** (OV, individual) | €69 first year + smartcard, ~€29 renewals; €189/yr cloud | ID verification (~1–2 weeks), then manual `signtool` per release; CI automation needs the pricier cloud tier | ❌ Money for a warning that stays anyway. Only worth revisiting if SignPath rejects the project. |
| **Azure Artifact Signing** (ex-Trusted Signing) | $9.99/mo | Smooth GitHub Actions integration | ❌ Ineligible: individuals only in USA/Canada (EU eligibility is organizations only). |
| **EV certificate** | $300–500/yr + registered legal entity | Highest paperwork | ❌ The instant-reputation benefit it used to buy no longer exists. |

## What the OSS community actually does

- **Most hobby-scale projects ship unsigned** and put the "More info → Run anyway" steps in the README. Even established projects have taken this position on principle (Inkscape: "we don't bother"). GitHub community threads show broad maintainer refusal to pay annual fees to prove free software isn't malware.
- Projects that want real signatures without money use **SignPath Foundation** (e.g. Super Productivity documents its policy publicly); it is the recognised community answer.
- A growing set of OSS apps publish to the **Microsoft Store** specifically to make the warning problem disappear for non-technical users.

## Decision (agreed 2026-07-05)

1. **Beta:** unsigned PyInstaller bundle; the SmartScreen click-through is documented in the pilot install instructions (this is the one step that may need sighted assistance, named explicitly).
2. **At first public release:** apply to SignPath Foundation; sign all direct-download bundles from then on so publisher reputation accrues continuously into V1.
3. **V1:** Microsoft Store as the primary zero-warning channel — budget $19 one-time; requires an MSIX spike (pynput global hook under `runFullTrust`) before committing. winget manifest as secondary channel.
4. **No paid certificate at any phase.** The roadmap's "~$200–500/yr cert" budget line is deleted, not deferred.

## Impact on existing docs (apply with the Beta-installable amendment)

- [roadmap.md](../roadmap.md) V1 list: replace the code-signing bullet (cert budget) with the Store/winget/SignPath plan above.
- [roadmap.md](../roadmap.md) Beta: the new unsigned-bundle item should reference this note for why unsigned is deliberate.
- New V1 spike item: MSIX/`runFullTrust` compatibility for pynput before Store commitment.

## Sources

- [Microsoft Learn — SmartScreen reputation for Windows app developers](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/smartscreen-reputation)
- [Microsoft Learn — code signing options for Windows developers](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/code-signing-options)
- [Microsoft Q&A — reputation with OV vs EV certificates](https://learn.microsoft.com/en-us/answers/questions/417016/reputation-with-ov-certificates-and-are-ev-certifi)
- [DigiCert — EV-signed apps still showing SmartScreen warnings](https://knowledge.digicert.com/alerts/ev-signed-application-showing-microsoft-defender-smartscreen-warnings)
- [SignPath Foundation — conditions for OSS projects](https://signpath.org/terms.html) · [example application (amd/gaia)](https://github.com/amd/gaia/issues/732)
- [Azure Artifact Signing — pricing](https://azure.microsoft.com/en-us/pricing/details/artifact-signing/) · [FAQ / eligibility](https://learn.microsoft.com/en-us/azure/artifact-signing/faq)
- [Certum — Open Source code signing](https://certum.store/open-source-code-signing-on-simplysign.html) · [walkthrough, Oct 2025](https://piers.rocks/2025/10/30/certum-open-source-code-sign.html)
- [GitHub community discussion #4293 — OSS devs vs certificate costs](https://github.com/orgs/community/discussions/4293)
- [winget-cli issue #3111 — SmartScreen and winget sources](https://github.com/microsoft/winget-cli/issues/3111)
- [The Register — unsigned-app friction on Windows 10 (incl. Inkscape quote)](https://www.theregister.com/2020/06/05/windows_10_microsoft_defender_smartscreen/)
