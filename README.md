# City Council support map: auto-updating, password-protected

Every hour, GitHub reads your Google Sheet, rebuilds the map, locks it behind a shared password and publishes it at a web address. You only ever edit the Sheet.

## One-time setup (about 15 minutes)

**1. Make a repository.** On github.com click **+ → New repository**. Name it (for example `council-map`) and choose **Public** (free Pages needs a public repo). Tick "Add a README" and create it.
The repository only holds code and settings. Your data never goes in it.

**2. Upload the code.** In the repo click **Add file → Upload files** and drag in `build_map.py`, `settings.py` and `requirements.txt`. Click **Commit changes**.

**3. Turn on Pages.** Repo **Settings → Pages → Build and deployment → Source: GitHub Actions**.

**4. Add your two secrets.** Repo **Settings → Secrets and variables → Actions → New repository secret**. Add:
- `SHEET_URL`: your Google Sheet link (it must be shared as **Anyone with the link: Viewer**).
- `MAP_PASSWORD`: the shared password. Use a long passphrase (4+ random words). The page is encrypted in the file itself, so a short password could be guessed offline.

**5. Add the workflow.** Click **Add file → Create new file**. In the name box type `.github/workflows/update-map.yml` (typing the slashes creates the folders). Paste in the full contents of `update-map.yml` from this zip, then **Commit changes**. It starts running immediately.

**6. Open the site.** Go to the **Actions** tab, click the latest "Update map" run, and when the `deploy` step finishes, the link appears under it. It looks like `https://YOUR-NAME.github.io/council-map/`. Send people the link and the password.

## Day to day
- **Edit the Sheet.** The map refreshes about once an hour.
- **Refresh right now:** Actions tab → **Update map** → **Run workflow**.
- **Change colors, labels, bills or column names:** open `settings.py` in the repo, click the pencil icon, edit, commit. The map rebuilds on its own.
- **Change the password:** update the `MAP_PASSWORD` secret, then run the workflow. Everyone has to enter the new one.

## Good to know
- **Scheduled runs pause after 60 days with no activity in the repo.** If the map stops refreshing, open the Actions tab and click Enable, or make any small edit.
- **Delays.** Scheduled runs can be late by several minutes.
- **If a build fails,** the last working map stays online. Click the failed run to see what it printed. Typical causes: the Sheet isn't shared by link, the tab name doesn't match `SHEET_TAB`, or a `MAP_PASSWORD` secret is missing. Cell problems (a misspelled status, a missing column) are printed as warnings.
- **Logs are public** on a public repo. The script only prints district numbers, column headers and bad cell values, never names, notes or your Sheet link.
- **Who can see what.** The password protects the published map. Anyone who has your Sheet link can read the Sheet itself, so don't share that link.
- **Old action versions.** If GitHub shows a warning about outdated action versions, bump the version numbers in `update-map.yml`.
